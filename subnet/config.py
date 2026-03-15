"""Subnet configuration constants with env-var override support."""

from __future__ import annotations

import os

from subnet import NETUID


def _env(key: str, default: str | int | float) -> str | int | float:
    """Return env var AXON_<key> cast to the same type as default, or default."""
    raw = os.environ.get(f"AXON_{key}")
    if raw is None:
        return default
    try:
        return type(default)(raw)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Scoring axis weights (must sum to 1.0)
# ---------------------------------------------------------------------------
TRAVERSAL_WEIGHT: float = float(_env("TRAVERSAL_WEIGHT", 0.40))
QUALITY_WEIGHT: float = float(_env("QUALITY_WEIGHT", 0.30))
TOPOLOGY_WEIGHT: float = float(_env("TOPOLOGY_WEIGHT", 0.15))
CORPUS_WEIGHT: float = float(_env("CORPUS_WEIGHT", 0.15))

# ---------------------------------------------------------------------------
# Traversal scoring
# ---------------------------------------------------------------------------
LATENCY_SOFT_LIMIT_S: float = float(_env("LATENCY_SOFT_LIMIT_S", 3.0))
LATENCY_PENALTY_PER_S: float = float(_env("LATENCY_PENALTY_PER_S", 0.1))
LATENCY_MAX_PENALTY: float = float(_env("LATENCY_MAX_PENALTY", 0.5))

# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------
MIN_HOP_WORDS: int = int(_env("MIN_HOP_WORDS", 100))
MAX_HOP_WORDS: int = int(_env("MAX_HOP_WORDS", 500))

# ---------------------------------------------------------------------------
# Topology scoring
# ---------------------------------------------------------------------------
BETWEENNESS_WEIGHT: float = float(_env("BETWEENNESS_WEIGHT", 0.6))
EDGE_WEIGHT_SUM_WEIGHT: float = float(_env("EDGE_WEIGHT_SUM_WEIGHT", 0.4))
EDGE_WEIGHT_CAP: int = int(_env("EDGE_WEIGHT_CAP", 50))

# ---------------------------------------------------------------------------
# Graph store
# ---------------------------------------------------------------------------
EDGE_DECAY_RATE: float = float(_env("EDGE_DECAY_RATE", 0.995))
EDGE_DECAY_FLOOR: float = float(_env("EDGE_DECAY_FLOOR", 0.01))

# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------
EPOCH_SLEEP_S: int = int(_env("EPOCH_SLEEP_S", 60))
MOVING_AVERAGE_ALPHA: float = float(_env("MOVING_AVERAGE_ALPHA", 0.1))
CHALLENGE_SAMPLE_SIZE: int = int(_env("CHALLENGE_SAMPLE_SIZE", 10))

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------
EMBEDDING_MODEL: str = str(_env("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"))
EMBEDDING_DIM: int = int(_env("EMBEDDING_DIM", 768))
EMBEDDING_BATCH_SIZE: int = int(_env("EMBEDDING_BATCH_SIZE", 32))

# ---------------------------------------------------------------------------
# Narrative miner (OpenRouter)
# ---------------------------------------------------------------------------
OPENROUTER_BASE_URL: str = str(_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
OPENROUTER_MODEL: str = str(_env("OPENROUTER_MODEL", "openrouter/auto"))

NARRATIVE_MODEL: str = str(_env("NARRATIVE_MODEL", OPENROUTER_MODEL))
NARRATIVE_MAX_TOKENS: int = int(_env("NARRATIVE_MAX_TOKENS", 400))
NARRATIVE_TEMPERATURE: float = float(_env("NARRATIVE_TEMPERATURE", 0.75))

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
ORCHESTRATOR_MAX_HOPS: int = int(_env("ORCHESTRATOR_MAX_HOPS", 8))
ORCHESTRATOR_MIN_MINERS: int = int(_env("ORCHESTRATOR_MIN_MINERS", 3))
ORCHESTRATOR_TIMEOUT_S: float = float(_env("ORCHESTRATOR_TIMEOUT_S", 12.0))

# ---------------------------------------------------------------------------
# Evolution / proposal / voting / pruning / integration
# ---------------------------------------------------------------------------
PROPOSAL_MIN_BOND_TAO: float = float(_env("PROPOSAL_MIN_BOND_TAO", 1.0))

# Voting windows (in blocks)
VOTING_OPEN_BLOCKS: int = int(_env("VOTING_OPEN_BLOCKS", 7200))   # ~24 h at 12 s/block
VOTING_QUORUM_RATIO: float = float(_env("VOTING_QUORUM_RATIO", 0.10))
VOTING_PASS_RATIO: float = float(_env("VOTING_PASS_RATIO", 0.60))

# Incubation
INCUBATION_BLOCKS: int = int(_env("INCUBATION_BLOCKS", 1800))     # ~6 h

# Pruning thresholds
PRUNING_MIN_EDGE_WEIGHT: float = float(_env("PRUNING_MIN_EDGE_WEIGHT", 0.05))
PRUNING_MIN_TRAVERSALS: int = int(_env("PRUNING_MIN_TRAVERSALS", 5))
PRUNING_INTERVAL_BLOCKS: int = int(_env("PRUNING_INTERVAL_BLOCKS", 3600))  # ~12 h

# Drift
DRIFT_MAX_COSINE_DISTANCE: float = float(_env("DRIFT_MAX_COSINE_DISTANCE", 0.35))

# Integration
INTEGRATION_BLOCKS: int = int(_env("INTEGRATION_BLOCKS", 600))    # ~2 h
INTEGRATION_MIN_SCORE: float = float(_env("INTEGRATION_MIN_SCORE", 0.50))

# ---------------------------------------------------------------------------
# Emission pool shares (must sum to 1.0)
# ---------------------------------------------------------------------------
EMISSION_TRAVERSAL_SHARE: float = float(_env("EMISSION_TRAVERSAL_SHARE", 0.50))
EMISSION_QUALITY_SHARE: float = float(_env("EMISSION_QUALITY_SHARE", 0.30))
EMISSION_TOPOLOGY_SHARE: float = float(_env("EMISSION_TOPOLOGY_SHARE", 0.20))


# ---------------------------------------------------------------------------
# SubnetConfig convenience wrapper
# ---------------------------------------------------------------------------
class SubnetConfig:
    """Snapshot of all subnet constants at import time.

    Attributes mirror module-level constants so callers can pass a single
    config object instead of importing individual names.
    """

    netuid: int = NETUID

    # Scoring weights
    traversal_weight: float = TRAVERSAL_WEIGHT
    quality_weight: float = QUALITY_WEIGHT
    topology_weight: float = TOPOLOGY_WEIGHT
    corpus_weight: float = CORPUS_WEIGHT

    # Traversal
    latency_soft_limit_s: float = LATENCY_SOFT_LIMIT_S
    latency_penalty_per_s: float = LATENCY_PENALTY_PER_S
    latency_max_penalty: float = LATENCY_MAX_PENALTY

    # Quality
    min_hop_words: int = MIN_HOP_WORDS
    max_hop_words: int = MAX_HOP_WORDS

    # Topology
    betweenness_weight: float = BETWEENNESS_WEIGHT
    edge_weight_sum_weight: float = EDGE_WEIGHT_SUM_WEIGHT
    edge_weight_cap: int = EDGE_WEIGHT_CAP

    # Graph store
    edge_decay_rate: float = EDGE_DECAY_RATE
    edge_decay_floor: float = EDGE_DECAY_FLOOR

    # Validator
    epoch_sleep_s: int = EPOCH_SLEEP_S
    moving_average_alpha: float = MOVING_AVERAGE_ALPHA
    challenge_sample_size: int = CHALLENGE_SAMPLE_SIZE

    # Embedding
    embedding_model: str = EMBEDDING_MODEL
    embedding_dim: int = EMBEDDING_DIM
    embedding_batch_size: int = EMBEDDING_BATCH_SIZE

    # Narrative miner
    openrouter_base_url: str = OPENROUTER_BASE_URL
    openrouter_model: str = OPENROUTER_MODEL
    narrative_model: str = NARRATIVE_MODEL
    narrative_max_tokens: int = NARRATIVE_MAX_TOKENS
    narrative_temperature: float = NARRATIVE_TEMPERATURE

    # Orchestrator
    orchestrator_max_hops: int = ORCHESTRATOR_MAX_HOPS
    orchestrator_min_miners: int = ORCHESTRATOR_MIN_MINERS
    orchestrator_timeout_s: float = ORCHESTRATOR_TIMEOUT_S

    # Evolution
    proposal_min_bond_tao: float = PROPOSAL_MIN_BOND_TAO
    voting_open_blocks: int = VOTING_OPEN_BLOCKS
    voting_quorum_ratio: float = VOTING_QUORUM_RATIO
    voting_pass_ratio: float = VOTING_PASS_RATIO
    incubation_blocks: int = INCUBATION_BLOCKS
    pruning_min_edge_weight: float = PRUNING_MIN_EDGE_WEIGHT
    pruning_min_traversals: int = PRUNING_MIN_TRAVERSALS
    pruning_interval_blocks: int = PRUNING_INTERVAL_BLOCKS
    drift_max_cosine_distance: float = DRIFT_MAX_COSINE_DISTANCE
    integration_blocks: int = INTEGRATION_BLOCKS
    integration_min_score: float = INTEGRATION_MIN_SCORE

    # Emission pool shares
    emission_traversal_share: float = EMISSION_TRAVERSAL_SHARE
    emission_quality_share: float = EMISSION_QUALITY_SHARE
    emission_topology_share: float = EMISSION_TOPOLOGY_SHARE


# Commit-reveal (configured on-chain via btcli sudo set)
# CommitRevealWeightsEnabled = True
# CommitRevealPeriod = 1
