"""Emission calculation for Bittensor Knowledge Network.

Three pools map miner performance to TAO emission weights:
  - TraversalPool  (40%): rewards high-traffic, low-latency nodes
  - QualityPool    (35%): rewards narrative quality scores
  - TopologyPool   (25%): rewards structurally important bridge nodes

Pool shares are configured in subnet/config.py (EMISSION_*_SHARE constants).

EmissionCalculator combines pools into the final weight vector submitted
to Yuma Consensus via set_weights().
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from subnet.config import (
    EMISSION_QUALITY_SHARE,
    EMISSION_TOPOLOGY_SHARE,
    EMISSION_TRAVERSAL_SHARE,
)

# ---------------------------------------------------------------------------
# Snapshot dataclass
# ---------------------------------------------------------------------------

@dataclass
class MinerScoreSnapshot:
    """Per-miner score snapshot for one epoch."""

    uid: int
    traversal_score: float = 0.0
    quality_score: float = 0.0
    topology_score: float = 0.0
    corpus_score: float = 1.0      # defaults to pass; zero triggers near-zero emission
    traversal_count: int = 0


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _softmax(values: list[float], temperature: float = 1.0) -> list[float]:
    """Softmax with temperature scaling. Returns uniform dist for empty input."""
    if not values:
        return []
    scaled = [v / temperature for v in values]
    max_v = max(scaled)
    exps = [math.exp(v - max_v) for v in scaled]
    total = sum(exps)
    if total == 0.0:
        return [1.0 / len(values)] * len(values)
    return [e / total for e in exps]


def _linear_normalise(values: list[float]) -> list[float]:
    """Normalise to sum=1 by dividing by total. Returns uniform for all-zero input."""
    if not values:
        return []
    total = sum(values)
    if total == 0.0:
        return [1.0 / len(values)] * len(values)
    return [v / total for v in values]


def _rank_normalise(values: list[float]) -> list[float]:
    """Convert values to rank-based weights (highest value -> highest rank)."""
    if not values:
        return []
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n
    for rank, (idx, _) in enumerate(indexed):
        ranks[idx] = float(rank + 1)
    return _linear_normalise(ranks)


# ---------------------------------------------------------------------------
# Pool classes
# ---------------------------------------------------------------------------

class TraversalPool:
    """Rewards miners with high traversal traffic and low latency.

    Weight = linear normalisation of per-miner traversal_score * traversal_count.
    """

    def weights(self, snapshots: list[MinerScoreSnapshot]) -> list[float]:
        raw = [s.traversal_score * max(s.traversal_count, 1) for s in snapshots]
        return _linear_normalise(raw)


class QualityPool:
    """Rewards miners producing high-quality narrative passages.

    Weight = softmax over quality scores (encourages competition).
    """

    def weights(self, snapshots: list[MinerScoreSnapshot]) -> list[float]:
        raw = [s.quality_score for s in snapshots]
        return _softmax(raw)


class TopologyPool:
    """Rewards structurally important bridge nodes (betweenness centrality proxy).

    Weight = rank normalisation over topology scores.
    """

    def weights(self, snapshots: list[MinerScoreSnapshot]) -> list[float]:
        raw = [s.topology_score for s in snapshots]
        return _rank_normalise(raw)


# ---------------------------------------------------------------------------
# Combined emission calculator
# ---------------------------------------------------------------------------

class EmissionCalculator:
    """Combine pool weights into a final normalised weight vector.

    Corpus score acts as a gate: if corpus_score == 0.0 the miner's
    combined weight is floored to near-zero, triggering eventual
    deregistration via Yuma Consensus.

    Args:
        traversal_share: Fraction of emission from TraversalPool.
        quality_share:   Fraction from QualityPool.
        topology_share:  Fraction from TopologyPool.
    """

    def __init__(
        self,
        traversal_share: float = EMISSION_TRAVERSAL_SHARE,
        quality_share: float = EMISSION_QUALITY_SHARE,
        topology_share: float = EMISSION_TOPOLOGY_SHARE,
    ) -> None:
        self._traversal_pool = TraversalPool()
        self._quality_pool = QualityPool()
        self._topology_pool = TopologyPool()
        self._traversal_share = traversal_share
        self._quality_share = quality_share
        self._topology_share = topology_share

    def compute(self, snapshots: list[MinerScoreSnapshot]) -> list[float]:
        """Return normalised weight vector aligned with snapshots order.

        Returns an all-zeros list if snapshots is empty.
        """
        if not snapshots:
            return []

        t_weights = self._traversal_pool.weights(snapshots)
        q_weights = self._quality_pool.weights(snapshots)
        top_weights = self._topology_pool.weights(snapshots)

        combined: list[float] = []
        for i, snap in enumerate(snapshots):
            score = (
                self._traversal_share * t_weights[i]
                + self._quality_share * q_weights[i]
                + self._topology_share * top_weights[i]
            )
            # Corpus gate: zero corpus score collapses weight to near-zero.
            if snap.corpus_score == 0.0:
                score = 1e-6
            combined.append(score)

        return _linear_normalise(combined)

    def compute_as_dict(
        self, snapshots: list[MinerScoreSnapshot]
    ) -> dict[int, float]:
        """Return {uid: weight} dict."""
        weights = self.compute(snapshots)
        return {snap.uid: w for snap, w in zip(snapshots, weights)}
