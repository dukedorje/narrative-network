"""Reward/scoring functions for the four scoring axes.

Each function takes miner responses and context, returns a float score in [0, 1].
"""

from __future__ import annotations

import math
import typing

from subnet.config import (
    BETWEENNESS_WEIGHT,
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
    merkle_root_matches: bool,
    partial_match: bool = False,
) -> float:
    """Score corpus integrity (weight: 0.15).

    Zero score triggers near-zero overall weight -> zero emission -> deregistration.
    """
    if merkle_root_matches:
        return 1.0
    elif partial_match:
        return 0.3
    else:
        return 0.0
