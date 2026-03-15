"""Integration manager for ramp-in of accepted NodeProposals.

After a proposal is ACCEPTED by the VotingEngine, it enters a multi-phase
integration pipeline:

  FORESHADOW -> BRIDGE -> RAMP -> LIVE

Foreshadowing: Miners attached to the new node receive advance notice so
  they can pre-load embeddings and corpus data.
Bridge: The node is added to the graph with edge_weight = 0 so traversals
  can begin routing to it (but scores are not yet committed to weights).
Ramp: Edge weight grows linearly from 0 to 1 over INTEGRATION_BLOCKS blocks.
Live: The node is fully integrated; the proposal's bond is returned.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum

from evolution.proposal import NodeProposal, ProposalStatus
from evolution.nla_settlement import NLASettlementClient
from orchestrator.unbrowse import UnbrowseClient
from subnet.config import INCUBATION_BLOCKS, INTEGRATION_BLOCKS, INTEGRATION_MIN_SCORE

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Integration phases (internal to this module; proposal uses ProposalStatus)
# ---------------------------------------------------------------------------

class _IntegrationPhase(str, Enum):
    FORESHADOW = "FORESHADOW"
    BRIDGE = "BRIDGE"
    RAMP = "RAMP"
    LIVE = "LIVE"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass
class IntegrationState:
    """Tracks integration progress for a single accepted proposal.

    Attributes:
        proposal_id: The proposal being integrated.
        node_id: Node being integrated into the graph.
        phase: Current integration phase.
        accepted_block: Block at which the proposal was accepted.
        bridge_block: Block at which the bridge phase started.
        ramp_start_block: Block at which ramping began.
        ramp_end_block: Block at which ramp completes (becomes LIVE).
        current_score: Rolling mean score used to gate go-live.
    """

    proposal_id: str
    node_id: str
    phase: _IntegrationPhase = _IntegrationPhase.FORESHADOW
    accepted_block: int = 0
    bridge_block: int = 0
    ramp_start_block: int = 0
    ramp_end_block: int = 0
    current_score: float = 0.0

    def edge_weight_at(self, current_block: int) -> float:
        """Return the current edge weight based on linear ramp progress.

        Returns:
            0.0 before ramping, linearly increasing during RAMP,
            1.0 once LIVE.
        """
        if self.phase == _IntegrationPhase.FORESHADOW:
            return 0.0
        if self.phase == _IntegrationPhase.BRIDGE:
            return 0.0
        if self.phase == _IntegrationPhase.LIVE:
            return 1.0
        # RAMP phase
        if self.ramp_end_block <= self.ramp_start_block:
            return 1.0
        elapsed = current_block - self.ramp_start_block
        duration = self.ramp_end_block - self.ramp_start_block
        return min(1.0, max(0.0, elapsed / duration))


@dataclass
class ForeshadowingNotice:
    """Notice sent to miners that a new node will soon be active.

    Attributes:
        node_id: The incoming node identifier.
        proposal_id: Source proposal.
        bridge_block: Expected block for bridge activation.
        metadata: Proposal metadata forwarded to miners (title, description, etc.).
    """

    node_id: str
    proposal_id: str
    bridge_block: int
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# IntegrationManager
# ---------------------------------------------------------------------------

class IntegrationManager:
    """Orchestrates the integration pipeline for accepted proposals.

    Args:
        incubation_blocks: Blocks between acceptance and bridge activation.
        integration_blocks: Blocks for the full ramp from 0 to 1 edge weight.
        min_score: Minimum rolling score required to advance to LIVE.
    """

    def __init__(
        self,
        incubation_blocks: int = INCUBATION_BLOCKS,
        integration_blocks: int = INTEGRATION_BLOCKS,
        min_score: float = INTEGRATION_MIN_SCORE,
    ) -> None:
        self.incubation_blocks = incubation_blocks
        self.integration_blocks = integration_blocks
        self.min_score = min_score

        # proposal_id -> IntegrationState
        self._queue: dict[str, IntegrationState] = {}
        # proposal_id -> NodeProposal
        self._proposals: dict[str, NodeProposal] = {}

        self._nla_client = NLASettlementClient()
        self._unbrowse = UnbrowseClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(self, proposal: NodeProposal, accepted_block: int) -> ForeshadowingNotice:
        """Enqueue an ACCEPTED proposal for integration.

        Immediately emits a ForeshadowingNotice for broadcast to miners.

        Args:
            proposal: The accepted NodeProposal.
            accepted_block: Block at which acceptance was recorded.

        Returns:
            ForeshadowingNotice to broadcast to miners attached to this node.

        Raises:
            ValueError: If proposal is not in ACCEPTED state.
        """
        if proposal.status != ProposalStatus.ACCEPTED:
            raise ValueError(
                f"Proposal {proposal.proposal_id} must be ACCEPTED to enqueue for integration"
            )

        bridge_block = accepted_block + self.incubation_blocks
        state = IntegrationState(
            proposal_id=proposal.proposal_id,
            node_id=proposal.node_id,
            phase=_IntegrationPhase.FORESHADOW,
            accepted_block=accepted_block,
            bridge_block=bridge_block,
            ramp_start_block=bridge_block,
            ramp_end_block=bridge_block + self.integration_blocks,
        )
        self._queue[proposal.proposal_id] = state
        self._proposals[proposal.proposal_id] = proposal

        notice = ForeshadowingNotice(
            node_id=proposal.node_id,
            proposal_id=proposal.proposal_id,
            bridge_block=bridge_block,
            metadata=proposal.metadata,
        )
        log.info(
            "Enqueued proposal %s for integration; foreshadow -> bridge at block %d",
            proposal.proposal_id,
            bridge_block,
        )
        proposal.status = ProposalStatus.INTEGRATING

        # Fire-and-forget: pre-fetch external web context for the new node
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._prefetch_node_context(
                    node_id=proposal.node_id,
                    domain=proposal.metadata.get("domain", proposal.node_id),
                    metadata=proposal.metadata,
                )
            )
        except RuntimeError:
            log.debug("No event loop — skipping Unbrowse prefetch for %s", proposal.node_id)

        return notice

    def process_epoch(
        self,
        current_block: int,
        node_scores: dict[str, float] | None = None,
    ) -> list[str]:
        """Advance all queued integrations. Return list of newly-live node IDs.

        Phase transitions:
        - FORESHADOW -> BRIDGE when current_block >= bridge_block
        - BRIDGE -> RAMP immediately (same epoch as bridge)
        - RAMP -> LIVE when current_block >= ramp_end_block AND score >= min_score

        Args:
            current_block: Current chain block.
            node_scores: Optional dict of node_id -> rolling mean score.
                         Used to gate RAMP -> LIVE transition.
        """
        newly_live: list[str] = []
        node_scores = node_scores or {}

        for pid, state in list(self._queue.items()):
            if state.phase == _IntegrationPhase.FORESHADOW:
                if current_block >= state.bridge_block:
                    state.phase = _IntegrationPhase.BRIDGE
                    log.info(
                        "Node %s entering BRIDGE phase at block %d",
                        state.node_id,
                        current_block,
                    )

            if state.phase == _IntegrationPhase.BRIDGE:
                # Immediately transition to RAMP in the same epoch
                state.ramp_start_block = current_block
                state.ramp_end_block = current_block + self.integration_blocks
                state.phase = _IntegrationPhase.RAMP
                log.info(
                    "Node %s entering RAMP phase; weight will reach 1.0 at block %d",
                    state.node_id,
                    state.ramp_end_block,
                )

            if state.phase == _IntegrationPhase.RAMP:
                state.current_score = node_scores.get(state.node_id, state.current_score)
                ramp_complete = current_block >= state.ramp_end_block
                score_ok = state.current_score >= self.min_score

                if ramp_complete and score_ok:
                    self._go_live(state, pid, current_block)
                    newly_live.append(state.node_id)
                elif ramp_complete and not score_ok:
                    log.warning(
                        "Node %s ramp complete but score %.3f < min %.3f; extending ramp by %d blocks",
                        state.node_id,
                        state.current_score,
                        self.min_score,
                        self.integration_blocks,
                    )
                    # Extend the ramp window to give the node more time
                    state.ramp_end_block = current_block + self.integration_blocks

        return newly_live

    def get_state(self, proposal_id: str) -> IntegrationState | None:
        """Return integration state for a proposal, or None if not found."""
        return self._queue.get(proposal_id)

    def active_integrations(self) -> list[IntegrationState]:
        """Return all integrations not yet LIVE."""
        return [s for s in self._queue.values() if s.phase != _IntegrationPhase.LIVE]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _go_live(self, state: IntegrationState, pid: str, current_block: int) -> None:
        state.phase = _IntegrationPhase.LIVE
        proposal = self._proposals.get(pid)
        log.info(
            "Node %s is LIVE at block %d (proposal %s)",
            state.node_id,
            current_block,
            pid,
        )
        if proposal is not None:
            proposal.status = ProposalStatus.LIVE
            # Settle NLA bond return on successful integration
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._settle_live_bond(proposal, current_block))
            except RuntimeError:
                log.warning("No event loop — skipping NLA settlement for proposal %s", pid)

    async def _prefetch_node_context(self, node_id: str, domain: str, metadata: dict) -> None:
        """Pre-fetch external web context for a new node during foreshadowing."""
        enrichment = await self._unbrowse.fetch_node_enrichment(
            node_id=node_id,
            domain=domain,
            metadata=metadata,
        )
        if enrichment:
            log.info(
                "Unbrowse prefetch for node %s: %d chars of external context",
                node_id,
                len(enrichment),
            )
        else:
            log.debug("Unbrowse prefetch returned no context for node %s", node_id)

    async def _settle_live_bond(self, proposal: "NodeProposal", live_block: int) -> None:
        """Settle NLA bond return when a node goes LIVE."""
        agreement = self._nla_client.build_integration_agreement(
            proposal_id=proposal.proposal_id,
            node_id=proposal.node_id,
            proposer_hotkey=proposal.proposer_hotkey,
            bond_tao=proposal.bond_tao,
            live_block=live_block,
        )
        await self._nla_client.register(agreement)
        await self._nla_client.settle(
            agreement=agreement,
            action="return",
            proposal_id=proposal.proposal_id,
            bond_tao=proposal.bond_tao,
            proposer_hotkey=proposal.proposer_hotkey,
        )
