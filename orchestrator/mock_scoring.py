"""Mock scoring functions for dev gateway — no live miners required.

Provides per-axis score approximations using local signals:
  - traversal: mean of chunk cosine similarity scores
  - quality: word count heuristic mapped to [0, 1]
  - topology: blended degree centrality + betweenness centrality
  - corpus: hardcoded 1.0 (all chunks are verified in-process)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from subnet.config import MAX_HOP_WORDS, MIN_HOP_WORDS

if TYPE_CHECKING:
    from subnet.graph_store import GraphStore


def mock_scores(
    chunk_scores: list[float],
    passage_text: str,
    node_id: str,
    graph_store: "GraphStore",
) -> dict[str, float]:
    """Compute mock axis scores for a single hop response.

    Args:
        chunk_scores: Cosine similarity scores for retrieved chunks (already computed).
        passage_text: The narrative passage generated for this hop.
        node_id: The destination node ID being scored.
        graph_store: Live graph store for topology signals.

    Returns:
        Dict with keys "traversal", "quality", "topology", "corpus" in [0, 1].
    """
    traversal = _score_traversal(chunk_scores)
    quality = _score_quality(passage_text)
    topology = _score_topology(node_id, graph_store)
    return {
        "traversal": traversal,
        "quality": quality,
        "topology": topology,
        "corpus": 1.0,
    }


def _score_traversal(chunk_scores: list[float]) -> float:
    """Mean of chunk cosine similarity scores, clipped to [0, 1]."""
    if not chunk_scores:
        return 0.0
    return float(np.clip(np.mean(chunk_scores), 0.0, 1.0))


def _score_quality(passage_text: str) -> float:
    """Word count heuristic mapped to [0, 1].

    Under MIN_HOP_WORDS -> 0.2
    Over MAX_HOP_WORDS -> 0.6
    In range [MIN, MAX] -> 1.0
    """
    word_count = len(passage_text.split())
    if word_count < MIN_HOP_WORDS:
        return 0.2
    if word_count > MAX_HOP_WORDS:
        return 0.6
    return 1.0


def _score_topology(node_id: str, graph_store: "GraphStore") -> float:
    """Blended degree centrality (0.4) + betweenness centrality (0.6).

    Degree is normalized by the maximum degree across all nodes.
    Betweenness is taken directly from brandes_betweenness (already in [0, 1]).
    Returns 0.0 if the node has no connections.
    """
    all_nodes = list(graph_store._mem._adj.keys())
    if not all_nodes:
        return 0.0

    # Degree centrality
    node_degree = len(graph_store.neighbours(node_id))
    max_degree = max(len(graph_store.neighbours(n)) for n in all_nodes)
    degree_norm = node_degree / max_degree if max_degree > 0 else 0.0

    # Betweenness centrality (Brandes — fast for small graphs)
    betweenness = graph_store._mem.brandes_betweenness()
    betweenness_score = betweenness.get(node_id, 0.0)

    return float(0.4 * degree_norm + 0.6 * betweenness_score)
