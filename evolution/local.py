"""Offline evolution subsystem — in-memory proposals, voting, and block counter."""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class LocalBlockClock:
    """Simulated block counter for offline evolution testing."""

    def __init__(self, start_block: int = 1000):
        self._block = start_block

    @property
    def current_block(self) -> int:
        return self._block

    def advance(self, n: int = 1) -> int:
        self._block += n
        return self._block


class LocalProposalSubmitter:
    """Standalone proposal submitter for offline mode. Uses composition, not inheritance.

    Does NOT subclass ProposalSubmitter because its constructor requires
    bt.Wallet and bt.Subtensor typed parameters. Instead, reimplements the
    proposal lifecycle (build -> submit) with in-memory state.
    """

    def __init__(
        self,
        hotkey: str = "local-validator",
        block_clock: LocalBlockClock | None = None,
    ):
        self.hotkey = hotkey
        self._clock = block_clock or LocalBlockClock()
        self._submitted: list = []

    def build_proposal(
        self,
        proposal_type,
        node_id: str,
        dest_node_id: str = "",
        metadata: dict | None = None,
        bond_tao: float = 0.1,
    ):
        """Build a new proposal in DRAFT state."""
        from evolution.proposal import NodeProposal, ProposalStatus

        proposal = NodeProposal(
            proposal_type=proposal_type,
            proposer_hotkey=self.hotkey,
            node_id=node_id,
            dest_node_id=dest_node_id,
            metadata=metadata or {},
            bond_tao=bond_tao,
            submitted_block=0,
            status=ProposalStatus.DRAFT,
        )
        return proposal

    def submit(self, proposal) -> object:
        """Submit a proposal: assign block, compute ID, transition to SUBMITTED."""
        from evolution.proposal import ProposalStatus

        proposal.submitted_block = self._clock.current_block
        proposal.proposal_id = proposal.compute_id()
        proposal.status = ProposalStatus.SUBMITTED
        self._submitted.append(proposal)
        log.info(
            "Local proposal %s submitted at block %d",
            proposal.proposal_id,
            proposal.submitted_block,
        )
        return proposal


from evolution.voting import VotingEngine  # noqa: E402


class LocalVotingEngine(VotingEngine):
    """VotingEngine subclass with fixed stake weights. Overrides _get_stake_weight().

    Bypasses the bt-availability guard in VotingEngine.__init__ by directly
    setting the same instance attributes, then uses MockSubtensor to satisfy
    any parent method that references self.subtensor.
    """

    def __init__(
        self,
        voter_hotkeys: list[str] | None = None,
        n_voters: int = 3,
        block_clock: LocalBlockClock | None = None,
        voting_open_blocks: int | None = None,
        quorum_ratio: float | None = None,
        pass_ratio: float | None = None,
    ):
        from subnet.config import VOTING_OPEN_BLOCKS, VOTING_PASS_RATIO, VOTING_QUORUM_RATIO
        from subnet.harness import MockMetagraph, MockSubtensor

        if voter_hotkeys is None:
            voter_hotkeys = [f"voter-{i}" for i in range(n_voters)]

        metagraph = MockMetagraph(n=len(voter_hotkeys))
        subtensor = MockSubtensor(metagraph=metagraph)

        # Use the parent constructor via the _BT_AVAILABLE-agnostic path:
        # MockSubtensor satisfies the bt.Subtensor type at runtime, and we
        # temporarily patch _BT_AVAILABLE to bypass the guard.
        import evolution.voting as _voting_mod
        _orig = _voting_mod._BT_AVAILABLE
        _voting_mod._BT_AVAILABLE = True
        try:
            super().__init__(
                subtensor=subtensor,
                netuid=0,
                voting_open_blocks=(
                    voting_open_blocks if voting_open_blocks is not None else VOTING_OPEN_BLOCKS
                ),
                quorum_ratio=(
                    quorum_ratio if quorum_ratio is not None else VOTING_QUORUM_RATIO
                ),
                pass_ratio=(
                    pass_ratio if pass_ratio is not None else VOTING_PASS_RATIO
                ),
            )
        finally:
            _voting_mod._BT_AVAILABLE = _orig

        self._clock = block_clock or LocalBlockClock()
        self._fixed_stakes = {hk: 1.0 / len(voter_hotkeys) for hk in voter_hotkeys}
        self._voter_hotkeys = list(voter_hotkeys)

    def _get_stake_weight(self, voter_hotkey: str) -> float:
        """Return fixed equal stake weight instead of metagraph lookup."""
        return self._fixed_stakes.get(voter_hotkey, 0.0)

    def _get_total_eligible_stake(self) -> float:
        """Return sum of all fixed stakes (always 1.0 for equal-weight voters)."""
        return sum(self._fixed_stakes.values())

    @property
    def voter_hotkeys(self) -> list[str]:
        return list(self._voter_hotkeys)
