"""Reward/scoring functions for the four scoring axes.

Each function takes miner responses and context, returns a float score in [0, 1].
"""

from __future__ import annotations

import math
import typing

from subnet.config import (
    BETWEENNESS_WEIGHT,
    CHOICE_CARD_MIN_COVERAGE,
    EDGE_WEIGHT_CAP,
    EDGE_WEIGHT_SUM_WEIGHT,
    LATENCY_MAX_PENALTY,
    LATENCY_PENALTY_PER_S,
    LATENCY_SOFT_LIMIT_S,
    MAX_HOP_WORDS,
    MIN_HOP_WORDS,
)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def score_traversal(
    chunks_embedding: list[float],
    query_embedding: list[float],
    domain_centroid: list[float],
    passage_embedding: list[float],
    process_time: float,
) -> float:
    """Score traversal quality (weight: 0.40).

    Measures chunk relevance and passage groundedness with latency penalty.
    """
    chunk_relevance = cosine_similarity(chunks_embedding, query_embedding)
    groundedness = cosine_similarity(passage_embedding, domain_centroid)

    latency_excess = max(0.0, process_time - LATENCY_SOFT_LIMIT_S)
    penalty = min(latency_excess * LATENCY_PENALTY_PER_S, LATENCY_MAX_PENALTY)

    raw = 0.6 * chunk_relevance + 0.4 * groundedness
    return max(0.0, raw * (1.0 - penalty))


def score_quality(
    passage_embedding: list[float],
    path_embeddings: list[list[float]],
    destination_centroid: list[float],
    source_centroid: list[float],
    passage_text: str,
) -> float:
    """Score narrative quality (weight: 0.30).

    Measures path coherence, directional progress, and passage length.
    """
    # Path coherence: similarity to running mean of path
    if path_embeddings:
        dim = len(path_embeddings[0])
        path_mean = [sum(e[i] for e in path_embeddings) / len(path_embeddings) for i in range(dim)]
        path_coherence = cosine_similarity(passage_embedding, path_mean)
    else:
        path_coherence = 0.5  # neutral for first hop

    # Directional progress
    dest_sim = cosine_similarity(passage_embedding, destination_centroid)
    src_sim = cosine_similarity(passage_embedding, source_centroid)
    directional_progress = max(0.0, dest_sim - src_sim)

    # Length heuristic (MVP)
    word_count = len(passage_text.split()) if passage_text else 0
    if word_count < MIN_HOP_WORDS:
        length_score = 0.2
    elif word_count > MAX_HOP_WORDS:
        length_score = 0.6
    else:
        length_score = 1.0

    return 0.4 * path_coherence + 0.3 * directional_progress + 0.3 * length_score


def score_choice_fairness(
    offered_node_ids: list[str],
    adjacent_node_ids: list[str],
    min_coverage: float = CHOICE_CARD_MIN_COVERAGE,
) -> float:
    """Score choice card fairness against the actual graph neighbourhood (multiplier).

    A coordinated set of narrative miners can starve nodes of traffic by never
    offering them as choice cards, which eventually triggers their pruning.
    This function returns a multiplier in [0, 1] that penalises miners who omit
    a large fraction of adjacent nodes from their choice cards.

    Parameters
    ----------
    offered_node_ids:
        Node IDs present in the choice cards returned by the miner.
        Only IDs that are also in adjacent_node_ids count toward coverage.
    adjacent_node_ids:
        The true set of outgoing neighbours for the current node, as reported
        by the graph store. Must not be empty for a meaningful score.
    min_coverage:
        The minimum fraction of adjacent nodes that must be offered. If
        coverage falls below this threshold the miner receives a reduced
        multiplier. Defaults to CHOICE_CARD_MIN_COVERAGE (0.5).

    Returns
    -------
    float
        1.0  — all adjacent nodes offered (full coverage).
        0.0  — no adjacent nodes offered at all.
        Linearly interpolated between 0 and min_coverage, then clamped to
        [0, 1]. Coverage above min_coverage returns 1.0 (no penalty).

    Notes
    -----
    - When there are no adjacent nodes the node is a terminal — return 1.0
      (no penalty; miner cannot be blamed for an empty neighbourhood).
    - The minimum required offered count is min(3, len(adjacent_node_ids)),
      consistent with MIN_CHOICE_CARDS in protocol.py.
    """
    if not adjacent_node_ids:
        # Terminal node — no penalty possible
        return 1.0

    adjacent_set = set(adjacent_node_ids)
    valid_offered = set(offered_node_ids) & adjacent_set
    coverage = len(valid_offered) / len(adjacent_set)

    # Hard floor: must offer at least min(3, len(adjacent)) choices
    min_required = min(3, len(adjacent_node_ids))
    if len(valid_offered) < min_required:
        # Scale linearly from 0 (zero offered) to min_coverage (min_required offered)
        return coverage / (min_required / len(adjacent_set))

    # Above the minimum count: score by coverage fraction
    if coverage >= min_coverage:
        return 1.0

    # Below min_coverage threshold: linear penalty from 0 at coverage=0 to 1 at coverage=min_coverage
    return coverage / min_coverage


def score_topology(
    betweenness_centrality: float,
    outgoing_edge_weight_sum: float,
) -> float:
    """Score topology importance (weight: 0.15).

    Rewards structurally important bridge nodes independent of traffic.
    """
    bc = min(betweenness_centrality, 1.0)
    ew = min(math.log1p(outgoing_edge_weight_sum) / math.log1p(EDGE_WEIGHT_CAP), 1.0)
    return BETWEENNESS_WEIGHT * bc + EDGE_WEIGHT_SUM_WEIGHT * ew


def score_corpus(
    proof_valid: bool = False,
    root_committed: bool = True,
    merkle_root_matches: bool | None = None,
    partial_match: bool = False,
) -> float:
    """Score corpus integrity (weight: 0.15).

    Parameters
    ----------
    proof_valid:
        True iff the Merkle inclusion proof is mathematically valid (hash chain
        from leaf through siblings equals the claimed root).
    root_committed:
        True iff the claimed root matches the previously committed root for this
        miner.  Defaults to True so callers that have no prior commitment still
        get credit for a valid proof.
    merkle_root_matches:
        Deprecated alias for proof_valid.  Ignored when proof_valid is
        explicitly supplied.
    partial_match:
        Deprecated partial-credit flag retained for backward compatibility.

    Zero score triggers near-zero overall weight -> zero emission -> deregistration.
    """
    # Back-compat: if called the old way (positional bool), treat it as proof_valid.
    if merkle_root_matches is not None and not proof_valid:
        proof_valid = merkle_root_matches

    if proof_valid and root_committed:
        return 1.0
    elif proof_valid and not root_committed:
        # Proof is mathematically sound but root changed — suspicious.
        return 0.3
    elif partial_match:
        return 0.3
    else:
        return 0.0
