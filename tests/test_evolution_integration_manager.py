"""Tests for evolution.integration.IntegrationManager.

Covers: enqueue, phase transitions (FORESHADOW->BRIDGE->RAMP->LIVE),
edge_weight_at ramp calculation, score-gated LIVE transition,
max ramp extensions, and integration collapse.
"""

import pytest

from evolution.integration import IntegrationManager, IntegrationState, _IntegrationPhase
from evolution.proposal import NodeProposal, ProposalStatus, ProposalType


def _make_accepted_proposal(node_id: str = "test-node", proposal_id: str = "p1") -> NodeProposal:
    p = NodeProposal(
        proposal_type=ProposalType.ADD_NODE,
        proposer_hotkey="proposer-hk",
        node_id=node_id,
        status=ProposalStatus.ACCEPTED,
        proposal_id=proposal_id,
        bond_tao=1.0,
    )
    return p


class TestEnqueue:
    def test_enqueue_sets_integrating_status(self):
        mgr = IntegrationManager(incubation_blocks=100, integration_blocks=200)
        proposal = _make_accepted_proposal()
        mgr.enqueue(proposal, accepted_block=1000)
        assert proposal.status == ProposalStatus.INTEGRATING

    def test_enqueue_returns_foreshadowing_notice(self):
        mgr = IntegrationManager(incubation_blocks=100, integration_blocks=200)
        proposal = _make_accepted_proposal()
        notice = mgr.enqueue(proposal, accepted_block=1000)
        assert notice.node_id == "test-node"
        assert notice.proposal_id == "p1"
        assert notice.bridge_block == 1100  # 1000 + 100

    def test_enqueue_rejects_non_accepted(self):
        mgr = IntegrationManager()
        proposal = _make_accepted_proposal()
        proposal.status = ProposalStatus.DRAFT
        with pytest.raises(ValueError, match="must be ACCEPTED"):
            mgr.enqueue(proposal, accepted_block=1000)

    def test_integrating_node_ids(self):
        mgr = IntegrationManager(incubation_blocks=10, integration_blocks=20)
        p1 = _make_accepted_proposal("node-a", "p1")
        p2 = _make_accepted_proposal("node-b", "p2")
        mgr.enqueue(p1, accepted_block=100)
        mgr.enqueue(p2, accepted_block=100)
        assert mgr.integrating_node_ids() == {"node-a", "node-b"}


class TestPhaseTransitions:
    def test_foreshadow_to_bridge_to_ramp(self):
        mgr = IntegrationManager(incubation_blocks=10, integration_blocks=50)
        proposal = _make_accepted_proposal()
        mgr.enqueue(proposal, accepted_block=100)

        state = mgr.get_state("p1")
        assert state.phase == _IntegrationPhase.FORESHADOW

        # Before bridge block — stays in FORESHADOW
        mgr.process_epoch(105)
        assert state.phase == _IntegrationPhase.FORESHADOW

        # At bridge block — transitions to RAMP (BRIDGE is transient)
        mgr.process_epoch(110)
        assert state.phase == _IntegrationPhase.RAMP

    def test_ramp_to_live_with_good_score(self):
        mgr = IntegrationManager(
            incubation_blocks=10, integration_blocks=50, min_score=0.5,
        )
        proposal = _make_accepted_proposal()
        mgr.enqueue(proposal, accepted_block=100)

        # Advance to RAMP
        mgr.process_epoch(110)
        state = mgr.get_state("p1")
        assert state.phase == _IntegrationPhase.RAMP

        # Advance past ramp end with good score
        newly_live = mgr.process_epoch(
            state.ramp_end_block + 1,
            node_scores={"test-node": 0.8},
        )
        assert state.phase == _IntegrationPhase.LIVE
        assert "test-node" in newly_live
        assert proposal.status == ProposalStatus.LIVE

    def test_ramp_extends_on_low_score(self):
        mgr = IntegrationManager(
            incubation_blocks=10, integration_blocks=50, min_score=0.5,
        )
        proposal = _make_accepted_proposal()
        mgr.enqueue(proposal, accepted_block=100)

        mgr.process_epoch(110)
        state = mgr.get_state("p1")
        original_end = state.ramp_end_block

        # Ramp complete but score too low — extends
        newly_live = mgr.process_epoch(
            original_end + 1,
            node_scores={"test-node": 0.3},
        )
        assert state.phase == _IntegrationPhase.RAMP
        assert newly_live == []
        assert state.ramp_extensions == 1
        assert state.ramp_end_block > original_end


class TestMaxRampExtensions:
    def test_collapses_after_max_extensions(self):
        mgr = IntegrationManager(
            incubation_blocks=10,
            integration_blocks=50,
            min_score=0.5,
            max_ramp_extensions=2,
        )
        proposal = _make_accepted_proposal()
        mgr.enqueue(proposal, accepted_block=100)

        # Advance to RAMP
        mgr.process_epoch(110)
        state = mgr.get_state("p1")

        # Extension 1
        mgr.process_epoch(state.ramp_end_block + 1, node_scores={"test-node": 0.1})
        assert state.ramp_extensions == 1

        # Extension 2
        mgr.process_epoch(state.ramp_end_block + 1, node_scores={"test-node": 0.1})
        assert state.ramp_extensions == 2

        # Extension 3 — should collapse (max=2)
        mgr.process_epoch(state.ramp_end_block + 1, node_scores={"test-node": 0.1})
        assert proposal.status == ProposalStatus.REJECTED
        assert mgr.get_state("p1") is None  # removed from queue


class TestEdgeWeight:
    def test_edge_weight_foreshadow(self):
        state = IntegrationState(
            proposal_id="p", node_id="n",
            phase=_IntegrationPhase.FORESHADOW,
        )
        assert state.edge_weight_at(100) == 0.0

    def test_edge_weight_bridge(self):
        state = IntegrationState(
            proposal_id="p", node_id="n",
            phase=_IntegrationPhase.BRIDGE,
        )
        assert state.edge_weight_at(100) == 0.0

    def test_edge_weight_ramp_midpoint(self):
        state = IntegrationState(
            proposal_id="p", node_id="n",
            phase=_IntegrationPhase.RAMP,
            ramp_start_block=100,
            ramp_end_block=200,
        )
        assert state.edge_weight_at(150) == pytest.approx(0.5)

    def test_edge_weight_live(self):
        state = IntegrationState(
            proposal_id="p", node_id="n",
            phase=_IntegrationPhase.LIVE,
        )
        assert state.edge_weight_at(100) == 1.0
