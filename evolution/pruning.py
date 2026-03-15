"""Pruning engine for node lifecycle management.

Tracks per-node epoch scores in a rolling window and transitions nodes
through a 3-phase state machine: HEALTHY -> WARNING -> DECAYING -> COLLAPSED.
Collapsed nodes are removed from the live graph.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from subnet.config import (
    PRUNING_MIN_TRAVERSALS,
)

log = logging.getLogger(__name__)

# Defaults configurable per-engine
DEFAULT_WINDOW_SIZE = 8          # epochs
DEFAULT_WARNING_THRESHOLD = 0.35  # score below this triggers WARNING
DEFAULT_DECAY_THRESHOLD = 0.20   # score below this escalates to DECAYING
DEFAULT_COLLAPSE_CONSECUTIVE = 3  # consecutive DECAYING epochs -> COLLAPSED


# ---------------------------------------------------------------------------
# Score window
# ---------------------------------------------------------------------------

@dataclass
class EpochScore:
    """Score record for one node in one epoch.

    Attributes:
        epoch: Epoch number.
        node_id: Node being scored.
        score: Composite score in [0, 1].
        traversal_count: Number of traversals through this node this epoch.
    """

    epoch: int
    node_id: str
    score: float
    traversal_count: int = 0


class ScoreWindow:
    """Rolling window of EpochScore records for a single node.

    Keeps the last ``max_size`` epoch scores and provides aggregate statistics.
    """

    def __init__(self, max_size: int = DEFAULT_WINDOW_SIZE) -> None:
        self._window: deque[EpochScore] = deque(maxlen=max_size)
        self.max_size = max_size

    def push(self, record: EpochScore) -> None:
        self._window.append(record)

    def mean(self) -> float:
        if not self._window:
            return 0.0
        return sum(r.score for r in self._window) / len(self._window)

    def trend(self) -> float:
        """Linear trend slope over the window (positive = improving).

        Returns 0.0 if fewer than 2 data points.
        """
        records = list(self._window)
        n = len(records)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2
        y_mean = sum(r.score for r in records) / n
        numerator = sum((i - x_mean) * (r.score - y_mean) for i, r in enumerate(records))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        return numerator / denominator if denominator else 0.0

    def consecutive_below(self, threshold: float) -> int:
        """Count consecutive recent epochs where score < threshold."""
        count = 0
        for record in reversed(list(self._window)):
            if record.score < threshold:
                count += 1
            else:
                break
        return count

    def total_traversals(self) -> int:
        return sum(r.traversal_count for r in self._window)

    def __len__(self) -> int:
        return len(self._window)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class PrunePhase(str, Enum):
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DECAYING = "DECAYING"
    COLLAPSED = "COLLAPSED"


@dataclass
class PruneState:
    """Current pruning state for a single node.

    Attributes:
        node_id: Node identifier.
        phase: Current phase.
        epochs_in_phase: Consecutive epochs in current phase.
        window: Rolling score window.
        last_epoch: Last epoch this state was updated.
    """

    node_id: str
    phase: PrunePhase = PrunePhase.HEALTHY
    epochs_in_phase: int = 0
    window: ScoreWindow = field(default_factory=ScoreWindow)
    last_epoch: int = 0


@dataclass
class CollapsePassage:
    """Record of a node collapse event.

    Attributes:
        node_id: Collapsed node.
        epoch: Epoch at which collapse was declared.
        final_mean_score: Rolling mean score at time of collapse.
        reason: Human-readable reason string.
    """

    node_id: str
    epoch: int
    final_mean_score: float
    reason: str


# ---------------------------------------------------------------------------
# PruningEngine
# ---------------------------------------------------------------------------

class PruningEngine:
    """Manages the pruning lifecycle for all active nodes.

    Args:
        window_size: Number of epochs in the rolling score window.
        warning_threshold: Mean score below this moves node to WARNING.
        decay_threshold: Mean score below this moves node to DECAYING.
        collapse_consecutive: Consecutive DECAYING epochs before COLLAPSED.
        min_traversals: Minimum traversals per window to avoid auto-collapse.
    """

    def __init__(
        self,
        window_size: int = DEFAULT_WINDOW_SIZE,
        warning_threshold: float = DEFAULT_WARNING_THRESHOLD,
        decay_threshold: float = DEFAULT_DECAY_THRESHOLD,
        collapse_consecutive: int = DEFAULT_COLLAPSE_CONSECUTIVE,
        min_traversals: int = PRUNING_MIN_TRAVERSALS,
    ) -> None:
        self.window_size = window_size
        self.warning_threshold = warning_threshold
        self.decay_threshold = decay_threshold
        self.collapse_consecutive = collapse_consecutive
        self.min_traversals = min_traversals

        # node_id -> PruneState
        self._states: dict[str, PruneState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_node(self, node_id: str) -> None:
        """Register a new node for pruning tracking."""
        if node_id not in self._states:
            self._states[node_id] = PruneState(
                node_id=node_id,
                window=ScoreWindow(max_size=self.window_size),
            )

    def push_scores(self, epoch: int, scores: dict[str, EpochScore]) -> None:
        """Push epoch scores for all nodes.

        Nodes not in ``scores`` receive a zero-score record to penalise inactivity.

        Args:
            epoch: Current epoch number.
            scores: Mapping of node_id -> EpochScore for active nodes.
        """
        for node_id, state in self._states.items():
            if state.phase == PrunePhase.COLLAPSED:
                continue
            record = scores.get(
                node_id,
                EpochScore(epoch=epoch, node_id=node_id, score=0.0, traversal_count=0),
            )
            state.window.push(record)
            state.last_epoch = epoch

    def process_epoch(self, epoch: int) -> list[CollapsePassage]:
        """Advance the state machine for all nodes. Return list of collapses.

        3-phase transitions:
        - HEALTHY: mean below warning_threshold -> WARNING
        - WARNING: mean below decay_threshold or still warning -> DECAYING
        - DECAYING: consecutive below decay_threshold >= collapse_consecutive -> COLLAPSED
        - Any phase: mean recovers above warning_threshold -> HEALTHY
        """
        collapses: list[CollapsePassage] = []

        for node_id, state in self._states.items():
            if state.phase == PrunePhase.COLLAPSED:
                continue

            mean = state.window.mean()
            traversals = state.window.total_traversals()

            # Insufficient activity check
            if len(state.window) >= self.window_size and traversals < self.min_traversals:
                passage = self._collapse(
                    state,
                    epoch,
                    mean,
                    reason=f"insufficient traversals ({traversals} < {self.min_traversals})",
                )
                collapses.append(passage)
                continue

            new_phase = self._compute_phase(state, mean)

            if new_phase == state.phase:
                state.epochs_in_phase += 1
            else:
                log.info(
                    "Node %s phase transition: %s -> %s (mean=%.3f epoch=%d)",
                    node_id,
                    state.phase.value,
                    new_phase.value,
                    mean,
                    epoch,
                )
                state.phase = new_phase
                state.epochs_in_phase = 1

            if state.phase == PrunePhase.DECAYING:
                consec = state.window.consecutive_below(self.decay_threshold)
                if consec >= self.collapse_consecutive:
                    passage = self._collapse(
                        state,
                        epoch,
                        mean,
                        reason=(
                            f"{consec} consecutive epochs below decay threshold {self.decay_threshold}"
                        ),
                    )
                    collapses.append(passage)

        return collapses

    def get_state(self, node_id: str) -> PruneState | None:
        return self._states.get(node_id)

    def live_nodes(self) -> list[str]:
        """Return node IDs that are not COLLAPSED."""
        return [
            nid for nid, s in self._states.items() if s.phase != PrunePhase.COLLAPSED
        ]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_phase(self, state: PruneState, mean: float) -> PrunePhase:
        if mean >= self.warning_threshold:
            return PrunePhase.HEALTHY
        if mean >= self.decay_threshold:
            return PrunePhase.WARNING
        return PrunePhase.DECAYING

    def _collapse(
        self,
        state: PruneState,
        epoch: int,
        mean: float,
        reason: str,
    ) -> CollapsePassage:
        state.phase = PrunePhase.COLLAPSED
        state.epochs_in_phase = 0
        log.warning(
            "Node %s COLLAPSED at epoch %d: %s (mean=%.3f)",
            state.node_id,
            epoch,
            reason,
            mean,
        )
        return CollapsePassage(
            node_id=state.node_id,
            epoch=epoch,
            final_mean_score=mean,
            reason=reason,
        )
