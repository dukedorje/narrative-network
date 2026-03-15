"""Voting engine for NodeProposal governance.

Validators cast weighted votes during the VOTING window. The VotingEngine
tallies results at epoch end, applies quorum and pass-ratio checks, and
transitions proposals to ACCEPTED or REJECTED. Rejected proposals trigger
bond burn; accepted proposals enter integration.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum

import bittensor as bt

from evolution.proposal import NodeProposal, ProposalStatus
from evolution.nla_settlement import NLASettlementClient, NLAgreement
from subnet.config import (
    VOTING_OPEN_BLOCKS,
    VOTING_QUORUM_RATIO,
    VOTING_PASS_RATIO,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and value objects
# ---------------------------------------------------------------------------

class VoteChoice(str, Enum):
    FOR = "FOR"
    AGAINST = "AGAINST"
    ABSTAIN = "ABSTAIN"


@dataclass
class Vote:
    """A single validator vote on a proposal.

    Attributes:
        proposal_id: Proposal being voted on.
        voter_hotkey: SS58 hotkey of the voting validator.
        choice: FOR / AGAINST / ABSTAIN.
        stake_weight: Normalised stake weight at vote time (0.0–1.0).
        block: Block at which the vote was cast.
    """

    proposal_id: str
    voter_hotkey: str
    choice: VoteChoice
    stake_weight: float
    block: int


@dataclass
class TallyResult:
    """Result of tallying all votes for a proposal.

    Attributes:
        proposal_id: Proposal tallied.
        for_weight: Sum of stake weights voting FOR.
        against_weight: Sum of stake weights voting AGAINST.
        abstain_weight: Sum of stake weights ABSTAINING.
        total_participating: Total stake weight of non-abstaining voters.
        quorum_met: Whether quorum threshold was reached.
        passed: Whether the proposal passed (quorum met and FOR > pass ratio).
    """

    proposal_id: str
    for_weight: float
    against_weight: float
    abstain_weight: float
    total_participating: float
    quorum_met: bool
    passed: bool

    @property
    def for_ratio(self) -> float:
        if self.total_participating == 0:
            return 0.0
        return self.for_weight / self.total_participating


# ---------------------------------------------------------------------------
# Bond return
# ---------------------------------------------------------------------------

class BondReturn:
    """Handles returning bonds to proposers on accepted or expired proposals.

    Both return_bond and burn_bond are sync-safe: they update proposal status
    immediately and schedule NLA settlement as a background task if an event
    loop is available. Callers do not need to await.
    """

    def __init__(self, subtensor: bt.Subtensor) -> None:
        self.subtensor = subtensor
        self.nla_client = NLASettlementClient()

    def return_bond(self, proposal: NodeProposal) -> None:
        """Return bond to proposer. Schedules NLA settlement in background."""
        log.info(
            "Returning %.4f TAO bond to %s for proposal %s",
            proposal.bond_tao,
            proposal.proposer_hotkey,
            proposal.proposal_id,
        )
        proposal.status = ProposalStatus.BOND_RETURNED
        self._schedule_settlement(proposal, action="return")

    def burn_bond(self, proposal: NodeProposal) -> None:
        """Burn bond on rejection. Schedules NLA settlement in background."""
        log.warning(
            "Burning %.4f TAO bond from %s for rejected proposal %s",
            proposal.bond_tao,
            proposal.proposer_hotkey,
            proposal.proposal_id,
        )
        self._schedule_settlement(proposal, action="burn")

    def _schedule_settlement(self, proposal: NodeProposal, action: str) -> None:
        """Schedule async NLA settlement if an event loop is running."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._settle_nla(proposal, action))
        except RuntimeError:
            log.debug(
                "No event loop — NLA settlement for %s deferred (action=%s)",
                proposal.proposal_id,
                action,
            )

    async def _settle_nla(self, proposal: NodeProposal, action: str) -> None:
        """Execute NLA settlement via Alkahest escrow."""
        agreement = proposal.nla_agreement
        if agreement is None:
            agreement = self.nla_client.build_proposal_agreement(
                proposal_id=proposal.proposal_id,
                proposer_hotkey=proposal.proposer_hotkey,
                node_id=proposal.node_id,
                proposal_type=proposal.proposal_type.value,
                bond_tao=proposal.bond_tao,
                voting_deadline_block=0,
            )
        await self.nla_client.settle(
            agreement=agreement,
            action=action,
            proposal_id=proposal.proposal_id,
            bond_tao=proposal.bond_tao,
            proposer_hotkey=proposal.proposer_hotkey,
        )


# ---------------------------------------------------------------------------
# VotingEngine
# ---------------------------------------------------------------------------

class VotingEngine:
    """Manages the full voting lifecycle for NodeProposals.

    Args:
        subtensor: Bittensor Subtensor connection for block queries.
        netuid: Subnet UID for stake lookups.
        voting_open_blocks: How many blocks the voting window stays open.
        quorum_ratio: Minimum participating stake fraction for a valid result.
        pass_ratio: Minimum FOR fraction of participating stake to pass.
    """

    def __init__(
        self,
        subtensor: bt.Subtensor,
        netuid: int,
        voting_open_blocks: int = VOTING_OPEN_BLOCKS,
        quorum_ratio: float = VOTING_QUORUM_RATIO,
        pass_ratio: float = VOTING_PASS_RATIO,
    ) -> None:
        self.subtensor = subtensor
        self.netuid = netuid
        self.voting_open_blocks = voting_open_blocks
        self.quorum_ratio = quorum_ratio
        self.pass_ratio = pass_ratio

        # proposal_id -> list[Vote]
        self._votes: dict[str, list[Vote]] = {}
        # proposal_id -> NodeProposal
        self._proposals: dict[str, NodeProposal] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_proposal(self, proposal: NodeProposal) -> None:
        """Register a submitted proposal for voting."""
        if proposal.status not in (ProposalStatus.SUBMITTED, ProposalStatus.VOTING):
            raise ValueError(
                f"Proposal {proposal.proposal_id} must be SUBMITTED or VOTING to register"
            )
        self._proposals[proposal.proposal_id] = proposal
        self._votes.setdefault(proposal.proposal_id, [])
        proposal.status = ProposalStatus.VOTING
        log.info("Proposal %s registered for voting", proposal.proposal_id)

        # Register NLA agreement on-chain when voting opens
        if proposal.nla_agreement is not None and proposal.nla_agreement.status == "draft":
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._register_nla(proposal))
            except RuntimeError:
                log.debug("No event loop — deferring NLA registration for %s", proposal.proposal_id)

    def cast_vote(
        self,
        proposal_id: str,
        voter_hotkey: str,
        choice: VoteChoice,
        current_block: int,
    ) -> Vote:
        """Cast a vote on a proposal.

        Stake weight is looked up from the metagraph at the time of casting.

        Raises:
            KeyError: If proposal_id is not registered.
            ValueError: If the voting window has closed or voter already voted.
        """
        proposal = self._proposals[proposal_id]
        self._check_window_open(proposal, current_block)
        self._check_no_duplicate(proposal_id, voter_hotkey)

        stake_weight = self._get_stake_weight(voter_hotkey)
        vote = Vote(
            proposal_id=proposal_id,
            voter_hotkey=voter_hotkey,
            choice=choice,
            stake_weight=stake_weight,
            block=current_block,
        )
        self._votes[proposal_id].append(vote)
        log.debug(
            "Vote cast: %s %s proposal=%s stake=%.4f",
            voter_hotkey[:8],
            choice.value,
            proposal_id,
            stake_weight,
        )
        return vote

    def tally(self, proposal_id: str) -> TallyResult:
        """Compute the current tally for a proposal without finalising."""
        votes = self._votes.get(proposal_id, [])
        for_w = sum(v.stake_weight for v in votes if v.choice == VoteChoice.FOR)
        against_w = sum(v.stake_weight for v in votes if v.choice == VoteChoice.AGAINST)
        abstain_w = sum(v.stake_weight for v in votes if v.choice == VoteChoice.ABSTAIN)
        participating = for_w + against_w

        quorum_met = participating >= self.quorum_ratio
        passed = quorum_met and (for_w / participating >= self.pass_ratio if participating > 0 else False)

        return TallyResult(
            proposal_id=proposal_id,
            for_weight=for_w,
            against_weight=against_w,
            abstain_weight=abstain_w,
            total_participating=participating,
            quorum_met=quorum_met,
            passed=passed,
        )

    def finalise(self, proposal: NodeProposal, current_block: int) -> TallyResult:
        """Close voting and apply the result to the proposal.

        Returns:
            TallyResult with final decision.
        """
        result = self.tally(proposal.proposal_id)
        if result.passed:
            proposal.status = ProposalStatus.ACCEPTED
            log.info(
                "Proposal %s ACCEPTED — for=%.3f quorum=%s",
                proposal.proposal_id,
                result.for_ratio,
                result.quorum_met,
            )
        else:
            proposal.status = ProposalStatus.REJECTED
            log.info(
                "Proposal %s REJECTED — for=%.3f quorum=%s",
                proposal.proposal_id,
                result.for_ratio,
                result.quorum_met,
            )
        return result

    def process_epoch(self, current_block: int) -> list[TallyResult]:
        """Finalise all proposals whose voting window has closed.

        Returns:
            List of TallyResult for each finalised proposal this epoch.
        """
        results: list[TallyResult] = []
        for proposal in list(self._proposals.values()):
            if proposal.status != ProposalStatus.VOTING:
                continue
            window_end = proposal.submitted_block + self.voting_open_blocks
            if current_block >= window_end:
                result = self.finalise(proposal, current_block)
                results.append(result)
        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _register_nla(self, proposal: NodeProposal) -> None:
        """Register the draft NLA agreement with the Arkhai service."""
        if proposal.nla_agreement is not None:
            client = NLASettlementClient()
            await client.register(proposal.nla_agreement)

    def _check_window_open(self, proposal: NodeProposal, current_block: int) -> None:
        window_end = proposal.submitted_block + self.voting_open_blocks
        if current_block >= window_end:
            raise ValueError(
                f"Voting window for proposal {proposal.proposal_id} closed at block {window_end}"
            )

    def _check_no_duplicate(self, proposal_id: str, voter_hotkey: str) -> None:
        existing = self._votes.get(proposal_id, [])
        if any(v.voter_hotkey == voter_hotkey for v in existing):
            raise ValueError(
                f"Hotkey {voter_hotkey} already voted on proposal {proposal_id}"
            )

    def _get_stake_weight(self, voter_hotkey: str) -> float:
        """Return normalised stake weight for a hotkey from the metagraph.

        TODO: Replace stub with real metagraph lookup.
        """
        try:
            metagraph = self.subtensor.metagraph(self.netuid)
            total_stake = sum(float(n.stake) for n in metagraph.neurons)
            for neuron in metagraph.neurons:
                if neuron.hotkey == voter_hotkey:
                    return float(neuron.stake) / total_stake if total_stake > 0 else 0.0
        except Exception as exc:
            log.warning("Could not fetch stake for %s: %s — using 0", voter_hotkey, exc)
        return 0.0
