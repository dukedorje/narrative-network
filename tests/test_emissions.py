"""Unit tests for subnet.emissions."""

from __future__ import annotations

import math

import pytest

from subnet.emissions import (
    EmissionCalculator,
    MinerScoreSnapshot,
    QualityPool,
    TopologyPool,
    TraversalPool,
    _linear_normalise,
    _rank_normalise,
    _softmax,
)


# ---------------------------------------------------------------------------
# _softmax
# ---------------------------------------------------------------------------


def test_softmax_basic():
    result = _softmax([1.0, 2.0, 3.0])
    assert len(result) == 3
    assert abs(sum(result) - 1.0) < 1e-9
    # Higher input -> higher output
    assert result[2] > result[1] > result[0]


def test_softmax_empty():
    assert _softmax([]) == []


def test_softmax_uniform():
    result = _softmax([5.0, 5.0, 5.0])
    assert len(result) == 3
    assert abs(sum(result) - 1.0) < 1e-9
    for v in result:
        assert abs(v - 1 / 3) < 1e-9


# ---------------------------------------------------------------------------
# _linear_normalise
# ---------------------------------------------------------------------------


def test_linear_normalise():
    result = _linear_normalise([1.0, 2.0, 3.0, 4.0])
    assert abs(sum(result) - 1.0) < 1e-9
    assert result[3] > result[2] > result[1] > result[0]


def test_linear_normalise_all_zero():
    result = _linear_normalise([0.0, 0.0, 0.0])
    assert abs(sum(result) - 1.0) < 1e-9
    for v in result:
        assert abs(v - 1 / 3) < 1e-9


# ---------------------------------------------------------------------------
# _rank_normalise
# ---------------------------------------------------------------------------


def test_rank_normalise():
    result = _rank_normalise([10.0, 30.0, 20.0])
    assert abs(sum(result) - 1.0) < 1e-9
    # 30.0 is highest -> index 1 gets highest rank weight
    assert result[1] > result[2] > result[0]


# ---------------------------------------------------------------------------
# TraversalPool
# ---------------------------------------------------------------------------


def test_traversal_pool():
    pool = TraversalPool()
    snaps = [
        MinerScoreSnapshot(uid=0, traversal_score=0.5, traversal_count=10),
        MinerScoreSnapshot(uid=1, traversal_score=0.9, traversal_count=50),
    ]
    weights = pool.weights(snaps)
    assert len(weights) == 2
    assert abs(sum(weights) - 1.0) < 1e-9
    # uid=1 has much higher score*count -> more weight
    assert weights[1] > weights[0]


# ---------------------------------------------------------------------------
# QualityPool
# ---------------------------------------------------------------------------


def test_quality_pool():
    pool = QualityPool()
    snaps = [
        MinerScoreSnapshot(uid=0, quality_score=0.3),
        MinerScoreSnapshot(uid=1, quality_score=0.9),
    ]
    weights = pool.weights(snaps)
    assert len(weights) == 2
    assert abs(sum(weights) - 1.0) < 1e-9
    # softmax amplifies the gap
    assert weights[1] > weights[0]


# ---------------------------------------------------------------------------
# TopologyPool
# ---------------------------------------------------------------------------


def test_topology_pool():
    pool = TopologyPool()
    snaps = [
        MinerScoreSnapshot(uid=0, topology_score=0.1),
        MinerScoreSnapshot(uid=1, topology_score=0.8),
        MinerScoreSnapshot(uid=2, topology_score=0.5),
    ]
    weights = pool.weights(snaps)
    assert len(weights) == 3
    assert abs(sum(weights) - 1.0) < 1e-9
    # Highest topology score -> highest rank weight
    assert weights[1] > weights[2] > weights[0]


# ---------------------------------------------------------------------------
# EmissionCalculator
# ---------------------------------------------------------------------------


def test_emission_calculator_basic():
    calc = EmissionCalculator()
    snaps = [
        MinerScoreSnapshot(uid=0, traversal_score=0.6, quality_score=0.7, topology_score=0.5),
        MinerScoreSnapshot(uid=1, traversal_score=0.4, quality_score=0.3, topology_score=0.2),
    ]
    weights = calc.compute(snaps)
    assert len(weights) == 2
    assert abs(sum(weights) - 1.0) < 1e-9
    for w in weights:
        assert w >= 0.0


def test_emission_calculator_corpus_gate():
    """corpus_score=0.0 collapses weight to 1e-6 before normalisation."""
    calc = EmissionCalculator()
    snaps = [
        MinerScoreSnapshot(
            uid=0,
            traversal_score=1.0,
            quality_score=1.0,
            topology_score=1.0,
            corpus_score=0.0,
        ),
        MinerScoreSnapshot(
            uid=1,
            traversal_score=0.5,
            quality_score=0.5,
            topology_score=0.5,
            corpus_score=1.0,
        ),
    ]
    weights = calc.compute(snaps)
    assert abs(sum(weights) - 1.0) < 1e-9
    # Cheating miner (uid=0) gets near-zero relative to honest miner
    assert weights[0] < 1e-3
    assert weights[1] > 0.99


def test_emission_calculator_empty():
    calc = EmissionCalculator()
    assert calc.compute([]) == []


def test_compute_as_dict():
    calc = EmissionCalculator()
    snaps = [
        MinerScoreSnapshot(uid=5, traversal_score=0.8, quality_score=0.6, topology_score=0.4),
        MinerScoreSnapshot(uid=7, traversal_score=0.2, quality_score=0.3, topology_score=0.1),
    ]
    result = calc.compute_as_dict(snaps)
    assert set(result.keys()) == {5, 7}
    assert abs(sum(result.values()) - 1.0) < 1e-9


def test_corpus_gate_dominates():
    """A miner with corpus_score=0 gets far less weight than an honest miner
    even if the cheating miner's other scores are higher."""
    calc = EmissionCalculator()
    snaps = [
        MinerScoreSnapshot(
            uid=0,
            traversal_score=1.0,
            quality_score=1.0,
            topology_score=1.0,
            corpus_score=0.0,   # cheating
            traversal_count=100,
        ),
        MinerScoreSnapshot(
            uid=1,
            traversal_score=0.1,
            quality_score=0.1,
            topology_score=0.1,
            corpus_score=1.0,   # honest
            traversal_count=1,
        ),
    ]
    weights = calc.compute(snaps)
    # Honest miner with low scores still dominates the cheater
    assert weights[1] > weights[0] * 100


# ---------------------------------------------------------------------------
# Pool totals sum to epoch emission
# ---------------------------------------------------------------------------


def test_emission_pools_sum_to_one():
    """All three pool weights, when combined with shares, sum to ~1.0."""
    snapshots = [
        MinerScoreSnapshot(uid=0, traversal_score=0.9, quality_score=0.8, topology_score=0.7, traversal_count=5),
        MinerScoreSnapshot(uid=1, traversal_score=0.5, quality_score=0.6, topology_score=0.3, traversal_count=3),
        MinerScoreSnapshot(uid=2, traversal_score=0.2, quality_score=0.3, topology_score=0.9, traversal_count=1),
    ]
    calculator = EmissionCalculator()
    weights = calculator.compute(snapshots)
    assert abs(sum(weights) - 1.0) < 1e-9


@pytest.mark.parametrize("t_share,q_share,top_share", [
    (0.5, 0.3, 0.2),
    (0.33, 0.33, 0.34),
    (0.8, 0.1, 0.1),
    (0.0, 0.5, 0.5),
    (1.0, 0.0, 0.0),
])
def test_emission_pools_sum_for_various_shares(t_share, q_share, top_share):
    """Pool totals sum to ~1.0 for various share combinations."""
    snapshots = [
        MinerScoreSnapshot(uid=0, traversal_score=0.9, quality_score=0.8, topology_score=0.5, traversal_count=3),
        MinerScoreSnapshot(uid=1, traversal_score=0.3, quality_score=0.6, topology_score=0.8, traversal_count=1),
    ]
    calculator = EmissionCalculator(
        traversal_share=t_share,
        quality_share=q_share,
        topology_share=top_share,
    )
    weights = calculator.compute(snapshots)
    assert abs(sum(weights) - 1.0) < 1e-9
