"""Tests for evolution.proposal — NodeProposal, ProposalSubmitter, NLA draft creation."""

from __future__ import annotations

import pytest

from evolution.proposal import (
    NodeProposal,
    ProposalStatus,
    ProposalSubmitter,
    ProposalType,
)
from tests.conftest import MockSubtensor, MockWallet


# ---------------------------------------------------------------------------
# NodeProposal identity helpers
# ---------------------------------------------------------------------------


class TestNodeProposalIdentity:
    def test_compute_id_is_deterministic(self):
        p = NodeProposal(
            proposal_type=ProposalType.ADD_NODE,
            proposer_hotkey="5GrwvaEF",
            node_id="quantum-01",
            submitted_block=1000,
        )
        assert p.compute_id() == p.compute_id()

    def test_compute_id_differs_for_different_blocks(self):
        base = NodeProposal(
            proposal_type=ProposalType.ADD_NODE,
            proposer_hotkey="5GrwvaEF",
            node_id="quantum-01",
            submitted_block=1000,
        )
        other = NodeProposal(
            proposal_type=ProposalType.ADD_NODE,
            proposer_hotkey="5GrwvaEF",
            node_id="quantum-01",
            submitted_block=2000,
        )
        assert base.compute_id() != other.compute_id()

    def test_commitment_hash_is_deterministic(self):
        p = NodeProposal(
            proposal_type=ProposalType.ADD_NODE,
            proposer_hotkey="5GrwvaEF",
            node_id="quantum-01",
            metadata={"title": "Test"},
            bond_tao=2.0,
            submitted_block=1000,
        )
        assert p.commitment_hash() == p.commitment_hash()

    def test_commitment_hash_64_hex_chars(self):
        p = NodeProposal(
            proposal_type=ProposalType.ADD_NODE,
            proposer_hotkey="hk",
            node_id="n1",
        )
        h = p.commitment_hash()
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_canonical_payload_includes_all_fields(self):
        p = NodeProposal(
            proposal_type=ProposalType.ADD_EDGE,
            proposer_hotkey="hk",
            node_id="src",
            dest_node_id="dst",
            bond_tao=1.5,
        )
        payload = p.canonical_payload()
        assert payload["dest_node_id"] == "dst"
        assert payload["bond_tao"] == 1.5


# ---------------------------------------------------------------------------
# ProposalSubmitter.build
# ---------------------------------------------------------------------------


class TestProposalSubmitterBuild:
    @pytest.fixture
    def submitter(self):
        wallet = MockWallet(hotkey_address="5GrwvaEF")
        subtensor = MockSubtensor()
        subtensor.get_current_block = lambda: 5000
        return ProposalSubmitter(wallet=wallet, subtensor=subtensor, netuid=0, min_bond_tao=1.0)

    def test_build_creates_draft(self, submitter):
        p = submitter.build(ProposalType.ADD_NODE, "quantum-01")
        assert p.status == ProposalStatus.DRAFT
        assert p.proposer_hotkey == "5GrwvaEF"
        assert p.bond_tao == 1.0

    def test_build_custom_bond(self, submitter):
        p = submitter.build(ProposalType.ADD_NODE, "n1", bond_tao=3.0)
        assert p.bond_tao == 3.0

    def test_build_below_min_bond_raises(self, submitter):
        with pytest.raises(ValueError, match="below minimum"):
            submitter.build(ProposalType.ADD_NODE, "n1", bond_tao=0.1)

    def test_build_add_edge_stores_dest(self, submitter):
        p = submitter.build(ProposalType.ADD_EDGE, "src", dest_node_id="dst")
        assert p.dest_node_id == "dst"


# ---------------------------------------------------------------------------
# ProposalSubmitter validation
# ---------------------------------------------------------------------------


class TestProposalSubmitterValidation:
    @pytest.fixture
    def submitter(self):
        wallet = MockWallet(hotkey_address="hk")
        subtensor = MockSubtensor()
        subtensor.get_current_block = lambda: 1000
        return ProposalSubmitter(wallet=wallet, subtensor=subtensor, netuid=0)

    def test_validate_empty_node_id_raises(self, submitter):
        p = NodeProposal(
            proposal_type=ProposalType.ADD_NODE, proposer_hotkey="hk", node_id=""
        )
        with pytest.raises(ValueError, match="node_id"):
            submitter._validate_proposal(p)

    def test_validate_add_edge_without_dest_raises(self, submitter):
        p = NodeProposal(
            proposal_type=ProposalType.ADD_EDGE, proposer_hotkey="hk", node_id="src"
        )
        with pytest.raises(ValueError, match="dest_node_id"):
            submitter._validate_proposal(p)

    def test_validate_non_draft_raises(self, submitter):
        p = NodeProposal(
            proposal_type=ProposalType.ADD_NODE,
            proposer_hotkey="hk",
            node_id="n1",
            status=ProposalStatus.VOTING,
        )
        with pytest.raises(ValueError, match="DRAFT"):
            submitter._validate_proposal(p)


# ---------------------------------------------------------------------------
# NLA draft created on _lock_bond
# ---------------------------------------------------------------------------


class TestNLADraftCreation:
    @pytest.fixture
    def submitter(self):
        wallet = MockWallet(hotkey_address="5GrwvaEF")
        subtensor = MockSubtensor()
        subtensor.get_current_block = lambda: 5000
        return ProposalSubmitter(wallet=wallet, subtensor=subtensor, netuid=0)

    def test_lock_bond_attaches_nla_agreement(self, submitter):
        p = NodeProposal(
            proposal_type=ProposalType.ADD_NODE,
            proposer_hotkey="5GrwvaEF",
            node_id="quantum-01",
            proposal_id="test-pid",
            bond_tao=2.0,
            submitted_block=5000,
        )
        submitter._lock_bond(p)
        assert p.nla_agreement is not None
        assert p.nla_agreement.status == "draft"
        assert p.nla_agreement.proposal_id == "test-pid"

    def test_nla_agreement_text_contains_bond_amount(self, submitter):
        p = NodeProposal(
            proposal_type=ProposalType.ADD_NODE,
            proposer_hotkey="5GrwvaEF",
            node_id="n1",
            proposal_id="pid",
            bond_tao=3.5,
            submitted_block=1000,
        )
        submitter._lock_bond(p)
        assert "3.5000 TAO" in p.nla_agreement.agreement_text
