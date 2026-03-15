"""Tests for evolution.voting — VotingEngine, BondReturn with NLA stubs."""

from __future__ import annotations

import pytest

from evolution.nla_settlement import NLAgreement
from evolution.proposal import NodeProposal, ProposalStatus, ProposalType
from evolution.voting import BondReturn, TallyResult, VoteChoice, VotingEngine
from tests.conftest import MockSubtensor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def subtensor():
    return MockSubtensor()


@pytest.fixture
def engine(subtensor):
    return VotingEngine(
        subtensor=subtensor,
        netuid=0,
        voting_open_blocks=100,
        quorum_ratio=0.10,
        pass_ratio=0.60,
    )


def _make_proposal(node_id: str = "n1", submitted_block: int = 0) -> NodeProposal:
    return NodeProposal(
        proposal_type=ProposalType.ADD_NODE,
        proposer_hotkey="hk-proposer",
        node_id=node_id,
        bond_tao=1.0,
        submitted_block=submitted_block,
        status=ProposalStatus.SUBMITTED,
    )


# ---------------------------------------------------------------------------
# VotingEngine.register_proposal
# ---------------------------------------------------------------------------


class TestRegisterProposal:
    def test_transitions_to_voting(self, engine):
        p = _make_proposal()
        p.proposal_id = "p1"
        engine.register_proposal(p)
        assert p.status == ProposalStatus.VOTING

    def test_duplicate_registration_idempotent(self, engine):
        p = _make_proposal()
        p.proposal_id = "p2"
        engine.register_proposal(p)
        engine.register_proposal(p)  # second call — same proposal in VOTING
        assert p.status == ProposalStatus.VOTING

    def test_raises_if_not_submitted(self, engine):
        p = _make_proposal()
        p.proposal_id = "p3"
        p.status = ProposalStatus.DRAFT
        with pytest.raises(ValueError, match="SUBMITTED or VOTING"):
            engine.register_proposal(p)


# ---------------------------------------------------------------------------
# VotingEngine.cast_vote
# ---------------------------------------------------------------------------


class TestCastVote:
    def test_cast_vote_recorded(self, engine, subtensor):
        p = _make_proposal(submitted_block=0)
        p.proposal_id = "pv1"
        # Patch metagraph for stake lookup
        subtensor._metagraph.hotkeys = ["validator-hk", "miner-hk"]
        subtensor._metagraph.S = [500.0, 100.0]
        engine.register_proposal(p)
        vote = engine.cast_vote("pv1", "validator-hk", VoteChoice.FOR, current_block=5)
        assert vote.choice == VoteChoice.FOR
        assert vote.voter_hotkey == "validator-hk"

    def test_duplicate_vote_raises(self, engine, subtensor):
        p = _make_proposal(submitted_block=0)
        p.proposal_id = "pv2"
        engine.register_proposal(p)
        engine.cast_vote("pv2", "hk1", VoteChoice.FOR, current_block=5)
        with pytest.raises(ValueError, match="already voted"):
            engine.cast_vote("pv2", "hk1", VoteChoice.AGAINST, current_block=6)

    def test_vote_after_window_raises(self, engine):
        p = _make_proposal(submitted_block=0)
        p.proposal_id = "pv3"
        engine.register_proposal(p)
        with pytest.raises(ValueError, match="closed"):
            engine.cast_vote("pv3", "hk1", VoteChoice.FOR, current_block=200)


# ---------------------------------------------------------------------------
# VotingEngine.tally
# ---------------------------------------------------------------------------


class TestTally:
    def _setup_votes(self, engine, proposal_id, for_weight, against_weight):
        from evolution.voting import Vote
        engine._votes[proposal_id] = []
        if for_weight > 0:
            engine._votes[proposal_id].append(
                Vote(
                    proposal_id=proposal_id,
                    voter_hotkey="for-voter",
                    choice=VoteChoice.FOR,
                    stake_weight=for_weight,
                    block=1,
                )
            )
        if against_weight > 0:
            engine._votes[proposal_id].append(
                Vote(
                    proposal_id=proposal_id,
                    voter_hotkey="against-voter",
                    choice=VoteChoice.AGAINST,
                    stake_weight=against_weight,
                    block=1,
                )
            )

    def test_tally_for_majority(self, engine):
        p = _make_proposal()
        p.proposal_id = "t1"
        engine._proposals["t1"] = p
        engine._votes["t1"] = []
        self._setup_votes(engine, "t1", for_weight=0.7, against_weight=0.1)
        result = engine.tally("t1")
        assert result.passed is True
        assert result.quorum_met is True
        assert result.for_ratio == pytest.approx(0.7 / 0.8)

    def test_tally_against_majority(self, engine):
        p = _make_proposal()
        p.proposal_id = "t2"
        engine._proposals["t2"] = p
        engine._votes["t2"] = []
        self._setup_votes(engine, "t2", for_weight=0.1, against_weight=0.5)
        result = engine.tally("t2")
        assert result.passed is False

    def test_tally_no_quorum(self, engine):
        p = _make_proposal()
        p.proposal_id = "t3"
        engine._proposals["t3"] = p
        engine._votes["t3"] = []
        # below 0.10 quorum
        self._setup_votes(engine, "t3", for_weight=0.05, against_weight=0.0)
        result = engine.tally("t3")
        assert result.quorum_met is False
        assert result.passed is False

    def test_tally_empty_votes(self, engine):
        p = _make_proposal()
        p.proposal_id = "t4"
        engine._proposals["t4"] = p
        engine._votes["t4"] = []
        result = engine.tally("t4")
        assert result.passed is False
        assert result.for_ratio == 0.0


# ---------------------------------------------------------------------------
# VotingEngine.finalise
# ---------------------------------------------------------------------------


class TestFinalise:
    def test_finalise_accepted(self, engine):
        p = _make_proposal()
        p.proposal_id = "f1"
        engine._proposals["f1"] = p
        from evolution.voting import Vote
        engine._votes["f1"] = [
            Vote("f1", "hk1", VoteChoice.FOR, stake_weight=0.8, block=1)
        ]
        result = engine.finalise(p, current_block=50)
        assert result.passed is True
        assert p.status == ProposalStatus.ACCEPTED

    def test_finalise_rejected(self, engine):
        p = _make_proposal()
        p.proposal_id = "f2"
        engine._proposals["f2"] = p
        from evolution.voting import Vote
        engine._votes["f2"] = [
            Vote("f2", "hk1", VoteChoice.AGAINST, stake_weight=0.8, block=1)
        ]
        result = engine.finalise(p, current_block=50)
        assert result.passed is False
        assert p.status == ProposalStatus.REJECTED


# ---------------------------------------------------------------------------
# VotingEngine.process_epoch
# ---------------------------------------------------------------------------


class TestProcessEpoch:
    def test_closes_expired_windows(self, engine):
        p = _make_proposal(submitted_block=0)
        p.proposal_id = "pe1"
        engine.register_proposal(p)
        results = engine.process_epoch(current_block=200)  # past window_end=100
        assert len(results) == 1
        assert p.status in (ProposalStatus.ACCEPTED, ProposalStatus.REJECTED)

    def test_does_not_close_open_window(self, engine):
        p = _make_proposal(submitted_block=0)
        p.proposal_id = "pe2"
        engine.register_proposal(p)
        results = engine.process_epoch(current_block=50)  # window still open
        assert results == []
        assert p.status == ProposalStatus.VOTING


# ---------------------------------------------------------------------------
# BondReturn — sync with background NLA settlement
# ---------------------------------------------------------------------------


class TestBondReturn:
    @pytest.fixture
    def bond_return(self, subtensor):
        return BondReturn(subtensor=subtensor)

    def test_return_bond_sets_bond_returned_status(self, bond_return):
        p = _make_proposal()
        p.proposal_id = "br1"
        p.nla_agreement = NLAgreement(agreement_text="test", proposal_id="br1")
        bond_return.return_bond(p)
        assert p.status == ProposalStatus.BOND_RETURNED

    def test_burn_bond_does_not_raise(self, bond_return):
        p = _make_proposal()
        p.proposal_id = "br2"
        p.nla_agreement = NLAgreement(agreement_text="test", proposal_id="br2")
        bond_return.burn_bond(p)  # should not raise

    def test_return_bond_without_agreement_creates_one(self, bond_return):
        """BondReturn should handle missing nla_agreement gracefully."""
        p = _make_proposal()
        p.proposal_id = "br3"
        p.nla_agreement = None
        bond_return.return_bond(p)
        assert p.status == ProposalStatus.BOND_RETURNED
