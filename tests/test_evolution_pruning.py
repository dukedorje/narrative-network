"""Tests for evolution.pruning — ScoreWindow, PruneState, PruningEngine with NLA stubs."""

from __future__ import annotations

import pytest

from evolution.pruning import (
    DEFAULT_COLLAPSE_CONSECUTIVE,
    DEFAULT_DECAY_THRESHOLD,
    DEFAULT_WARNING_THRESHOLD,
    DEFAULT_WINDOW_SIZE,
    CollapsePassage,
    EpochScore,
    PrunePhase,
    PruneState,
    PruningEngine,
    ScoreWindow,
)


# ---------------------------------------------------------------------------
# ScoreWindow
# ---------------------------------------------------------------------------


class TestScoreWindow:
    def test_mean_empty(self):
        w = ScoreWindow(max_size=5)
        assert w.mean() == 0.0

    def test_mean_single(self):
        w = ScoreWindow(max_size=5)
        w.push(EpochScore(epoch=1, node_id="n", score=0.8))
        assert w.mean() == pytest.approx(0.8)

    def test_mean_multiple(self):
        w = ScoreWindow(max_size=5)
        for i, s in enumerate([0.6, 0.8, 0.4]):
            w.push(EpochScore(epoch=i, node_id="n", score=s))
        assert w.mean() == pytest.approx(0.6)

    def test_max_size_evicts_oldest(self):
        w = ScoreWindow(max_size=3)
        for i in range(5):
            w.push(EpochScore(epoch=i, node_id="n", score=float(i)))
        assert len(w) == 3
        assert w.mean() == pytest.approx((2.0 + 3.0 + 4.0) / 3)

    def test_trend_positive(self):
        w = ScoreWindow(max_size=5)
        for i, s in enumerate([0.1, 0.3, 0.5, 0.7]):
            w.push(EpochScore(epoch=i, node_id="n", score=s))
        assert w.trend() > 0

    def test_trend_negative(self):
        w = ScoreWindow(max_size=5)
        for i, s in enumerate([0.9, 0.7, 0.5, 0.3]):
            w.push(EpochScore(epoch=i, node_id="n", score=s))
        assert w.trend() < 0

    def test_trend_single_point_is_zero(self):
        w = ScoreWindow(max_size=5)
        w.push(EpochScore(epoch=0, node_id="n", score=0.5))
        assert w.trend() == 0.0

    def test_consecutive_below_threshold(self):
        w = ScoreWindow(max_size=6)
        for i, s in enumerate([0.8, 0.8, 0.1, 0.1, 0.1]):
            w.push(EpochScore(epoch=i, node_id="n", score=s))
        assert w.consecutive_below(0.3) == 3

    def test_consecutive_below_reset_by_recovery(self):
        w = ScoreWindow(max_size=6)
        for i, s in enumerate([0.1, 0.1, 0.9]):
            w.push(EpochScore(epoch=i, node_id="n", score=s))
        assert w.consecutive_below(0.3) == 0

    def test_total_traversals(self):
        w = ScoreWindow(max_size=5)
        for i in range(3):
            w.push(EpochScore(epoch=i, node_id="n", score=0.5, traversal_count=10))
        assert w.total_traversals() == 30


# ---------------------------------------------------------------------------
# PruningEngine — node lifecycle
# ---------------------------------------------------------------------------


class TestPruningEngine:
    @pytest.fixture
    def engine(self):
        return PruningEngine(
            window_size=4,
            warning_threshold=DEFAULT_WARNING_THRESHOLD,
            decay_threshold=DEFAULT_DECAY_THRESHOLD,
            collapse_consecutive=DEFAULT_COLLAPSE_CONSECUTIVE,
            min_traversals=2,
        )

    def test_register_node(self, engine):
        engine.register_node("n1")
        state = engine.get_state("n1")
        assert state is not None
        assert state.phase == PrunePhase.HEALTHY

    def test_register_node_with_bond_info(self, engine):
        engine.register_node("n2", proposer_hotkey="5abc", bond_tao=2.0)
        state = engine.get_state("n2")
        assert state.proposer_hotkey == "5abc"
        assert state.bond_tao == pytest.approx(2.0)

    def test_register_idempotent(self, engine):
        engine.register_node("n3")
        engine.register_node("n3")  # second call — no error, no duplicate
        assert engine.get_state("n3") is not None

    def test_healthy_stays_healthy_above_threshold(self, engine):
        engine.register_node("n1")
        for epoch in range(4):
            engine.push_scores(epoch, {"n1": EpochScore(epoch=epoch, node_id="n1", score=0.9, traversal_count=5)})
        collapses = engine.process_epoch(epoch=4)
        assert engine.get_state("n1").phase == PrunePhase.HEALTHY
        assert collapses == []

    def test_below_warning_transitions_to_warning(self, engine):
        engine.register_node("n1")
        for epoch in range(4):
            engine.push_scores(epoch, {"n1": EpochScore(epoch=epoch, node_id="n1", score=0.25, traversal_count=5)})
        engine.process_epoch(epoch=4)
        assert engine.get_state("n1").phase in (PrunePhase.WARNING, PrunePhase.DECAYING)

    def test_consecutive_decaying_triggers_collapse(self, engine):
        engine.register_node("n1")
        # Push 4 epochs of very low scores (below decay_threshold=0.20)
        for epoch in range(4):
            engine.push_scores(
                epoch,
                {"n1": EpochScore(epoch=epoch, node_id="n1", score=0.05, traversal_count=5)},
            )
            collapses = engine.process_epoch(epoch=epoch)

        state = engine.get_state("n1")
        # After 3+ consecutive decaying epochs the node should be collapsed
        assert state.phase == PrunePhase.COLLAPSED

    def test_collapse_returns_passage(self, engine):
        engine.register_node("n1")
        for epoch in range(4):
            engine.push_scores(
                epoch,
                {"n1": EpochScore(epoch=epoch, node_id="n1", score=0.05, traversal_count=5)},
            )
        last_collapses = engine.process_epoch(epoch=3)
        # At some point we should have gotten a CollapsePassage
        all_collapses = []
        for ep in range(4):
            engine2 = PruningEngine(window_size=4, min_traversals=2, collapse_consecutive=3)
            engine2.register_node("nc")
            for e in range(ep + 1):
                engine2.push_scores(
                    e, {"nc": EpochScore(epoch=e, node_id="nc", score=0.05, traversal_count=5)}
                )
            c = engine2.process_epoch(epoch=ep)
            all_collapses.extend(c)
        assert any(isinstance(c, CollapsePassage) for c in all_collapses)

    def test_insufficient_traversals_collapses(self, engine):
        engine.register_node("n1")
        # 4 epochs, only 1 traversal per epoch (< min_traversals=2 * window=4 = need 2 total for window)
        for epoch in range(4):
            engine.push_scores(
                epoch,
                {"n1": EpochScore(epoch=epoch, node_id="n1", score=0.9, traversal_count=0)},
            )
            collapses = engine.process_epoch(epoch=epoch)
        assert engine.get_state("n1").phase == PrunePhase.COLLAPSED

    def test_recovery_from_warning_to_healthy(self, engine):
        engine.register_node("n1")
        # 2 bad epochs
        for epoch in range(2):
            engine.push_scores(epoch, {"n1": EpochScore(epoch=epoch, node_id="n1", score=0.25, traversal_count=5)})
            engine.process_epoch(epoch=epoch)
        # 4 good epochs — should recover
        for epoch in range(2, 6):
            engine.push_scores(epoch, {"n1": EpochScore(epoch=epoch, node_id="n1", score=0.95, traversal_count=10)})
            engine.process_epoch(epoch=epoch)
        assert engine.get_state("n1").phase == PrunePhase.HEALTHY

    def test_collapsed_node_not_in_live_nodes(self, engine):
        engine.register_node("live")
        engine.register_node("dead")
        engine.get_state("dead").phase = PrunePhase.COLLAPSED
        assert "live" in engine.live_nodes()
        assert "dead" not in engine.live_nodes()

    def test_missing_scores_penalised_with_zero(self, engine):
        engine.register_node("n1")
        engine.register_node("n2")
        # Only push for n1; n2 gets zero penalty
        engine.push_scores(0, {"n1": EpochScore(epoch=0, node_id="n1", score=0.9, traversal_count=5)})
        assert engine.get_state("n2").window.mean() == 0.0


# ---------------------------------------------------------------------------
# NLA stub — collapse fires async task without raising
# ---------------------------------------------------------------------------


class TestCollapseNLAStub:
    async def test_collapse_does_not_raise_without_api_key(self):
        """PruningEngine._collapse fires NLA task but never blocks/raises."""
        engine = PruningEngine(
            window_size=4,
            min_traversals=2,
            collapse_consecutive=3,
        )
        engine.register_node("n1", proposer_hotkey="5abc", bond_tao=1.0)
        for epoch in range(4):
            engine.push_scores(
                epoch,
                {"n1": EpochScore(epoch=epoch, node_id="n1", score=0.01, traversal_count=5)},
            )
            # Should not raise even though NLA API key is absent
            engine.process_epoch(epoch=epoch)

        state = engine.get_state("n1")
        assert state.phase == PrunePhase.COLLAPSED
