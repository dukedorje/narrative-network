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

# Choice card fairness: miner must offer at least this fraction of adjacent nodes
# as valid choice cards (0.5 = must offer at least half of adjacent nodes).
# A miner scoring below this threshold receives a penalty multiplier on quality_score.
CHOICE_CARD_MIN_COVERAGE: float = float(_env("CHOICE_CARD_MIN_COVERAGE", 0.5))

# ---------------------------------------------------------------------------
# Topology scoring
# ---------------------------------------------------------------------------
BETWEENNESS_WEIGHT: float = float(_env("BETWEENNESS_WEIGHT", 0.6))
EDGE_WEIGHT_SUM_WEIGHT: float = float(_env("EDGE_WEIGHT_SUM_WEIGHT", 0.4))
EDGE_WEIGHT_CAP: int = int(_env("EDGE_WEIGHT_CAP", 50))

# ---------------------------------------------------------------------------
# Graph store
# ---------------------------------------------------------------------------
# Edge decay is applied once per epoch (EPOCH_SLEEP_S = 60s => ~1440 epochs/day).
#
# Decay math (rate r, floor f=0.01):
#   - Epochs to floor  = log(f) / log(r)
#   - Half-life epochs = log(0.5) / log(r)
#
# Old default 0.995: floor reached in ~920 epochs (~15 h). Too aggressive.
#
# New default 0.9996:
#   - Floor reached in ~11 500 epochs (~8 days of zero traversal)
#   - Half-life ~1 730 epochs (~1.2 days)
#
# Operators can tune via AXON_EDGE_DECAY_RATE. A higher value (closer to 1.0)
# gives a longer half-life; a lower value kills idle edges faster.
EDGE_DECAY_RATE: float = float(_env("EDGE_DECAY_RATE", 0.9996))
EDGE_DECAY_FLOOR: float = float(_env("EDGE_DECAY_FLOOR", 0.01))

# Derived constant for operator intuition (read-only; not env-overridable).
# At 1440 epochs/day: half-life ≈ 1.2 days; floor reached ≈ 8 days.
import math as _math
EDGE_DECAY_HALF_LIFE_EPOCHS: int = round(_math.log(0.5) / _math.log(EDGE_DECAY_RATE))

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
EMBEDDING_CACHE_DIR: str = str(_env("EMBEDDING_CACHE_DIR", "/data/embedding_cache"))

# ---------------------------------------------------------------------------
# Narrative miner (OpenRouter)
# ---------------------------------------------------------------------------
OPENROUTER_BASE_URL: str = str(_env("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"))
OPENROUTER_MODEL: str = str(_env("OPENROUTER_MODEL", "anthropic/claude-3.5-haiku"))

NARRATIVE_MODEL: str = str(_env("NARRATIVE_MODEL", OPENROUTER_MODEL))
NARRATIVE_MAX_TOKENS: int = int(_env("NARRATIVE_MAX_TOKENS", 1024))
NARRATIVE_TEMPERATURE: float = float(_env("NARRATIVE_TEMPERATURE", 0.75))

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
ORCHESTRATOR_MAX_HOPS: int = int(_env("ORCHESTRATOR_MAX_HOPS", 8))
ORCHESTRATOR_MIN_MINERS: int = int(_env("ORCHESTRATOR_MIN_MINERS", 3))
ORCHESTRATOR_TIMEOUT_S: float = float(_env("ORCHESTRATOR_TIMEOUT_S", 12.0))

# Session TTL (seconds) — applies to both gateway and narrative session stores
SESSION_TTL_S: int = int(_env("SESSION_TTL_S", 1800))

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
#
# PRUNING_INTERVAL_BLOCKS is block-based (1 block ≈ 12 s on Bittensor mainnet):
#   3600 blocks * 12 s/block = ~12 h between pruning runs.
#
# DEFAULT_WINDOW_SIZE and DEFAULT_COLLAPSE_CONSECUTIVE in evolution/pruning.py
# are epoch-based (1 epoch = EPOCH_SLEEP_S = 60 s):
#   window 720 epochs  = 720 * 60 s = ~12 h of score history
#   collapse 24 epochs = 24 consecutive epochs below threshold ≈ 24 min
#   (pruning_engine is called once per epoch by the validator loop)
#
# PRUNING_MIN_TRAVERSALS is measured over the window (720 epochs ≈ 12 h).
# The old value of 5 was reasonable in absolute terms but the window was only
# 8 epochs (~8 min), making the bar impossibly high during quiet periods.
# With a 720-epoch window the same absolute count is much more forgiving.
# Operators running very high-traffic subnets can raise this via
# AXON_PRUNING_MIN_TRAVERSALS.
PRUNING_MIN_EDGE_WEIGHT: float = float(_env("PRUNING_MIN_EDGE_WEIGHT", 0.05))
PRUNING_MIN_TRAVERSALS: int = int(_env("PRUNING_MIN_TRAVERSALS", 5))
PRUNING_INTERVAL_BLOCKS: int = int(_env("PRUNING_INTERVAL_BLOCKS", 3600))  # ~12 h at 12 s/block

# Drift
DRIFT_MAX_COSINE_DISTANCE: float = float(_env("DRIFT_MAX_COSINE_DISTANCE", 0.35))

# Integration
INTEGRATION_BLOCKS: int = int(_env("INTEGRATION_BLOCKS", 600))    # ~2 h
INTEGRATION_MIN_SCORE: float = float(_env("INTEGRATION_MIN_SCORE", 0.50))

# Node registration via manifest
NODE_REGISTRATION_ENABLED: bool = bool(int(_env("NODE_REGISTRATION_ENABLED", 1)))
PRUNING_ENABLED: bool = bool(int(_env("PRUNING_ENABLED", 1)))
PRUNING_EPOCH_INTERVAL: int = int(_env("PRUNING_EPOCH_INTERVAL", 10))

# ---------------------------------------------------------------------------
# Natural Language Agreements (Arkhai Alkahest)
# ---------------------------------------------------------------------------
NLA_ENDPOINT: str = str(_env("NLA_ENDPOINT", "https://api.arkhai.io/nla"))
NLA_CHAIN: str = str(_env("NLA_CHAIN", "base"))

# ---------------------------------------------------------------------------
# Unbrowse.ai (external web context layer)
# ---------------------------------------------------------------------------
UNBROWSE_API_URL: str = str(_env("UNBROWSE_API_URL", "https://api.unbrowse.ai"))
UNBROWSE_TIMEOUT_S: float = float(_env("UNBROWSE_TIMEOUT_S", 8.0))
# Corpus similarity score below this triggers Unbrowse external context fetch
UNBROWSE_CORPUS_THRESHOLD: float = float(_env("UNBROWSE_CORPUS_THRESHOLD", 0.35))

# ---------------------------------------------------------------------------
# Emission pool shares (must sum to 1.0)
# ---------------------------------------------------------------------------
EMISSION_TRAVERSAL_SHARE: float = float(_env("EMISSION_TRAVERSAL_SHARE", 0.40))
EMISSION_QUALITY_SHARE: float = float(_env("EMISSION_QUALITY_SHARE", 0.35))
EMISSION_TOPOLOGY_SHARE: float = float(_env("EMISSION_TOPOLOGY_SHARE", 0.25))


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
    choice_card_min_coverage: float = CHOICE_CARD_MIN_COVERAGE

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
    session_ttl_s: int = SESSION_TTL_S

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

    # Natural Language Agreements
    nla_endpoint: str = NLA_ENDPOINT
    nla_chain: str = NLA_CHAIN

    # Unbrowse
    unbrowse_api_url: str = UNBROWSE_API_URL
    unbrowse_timeout_s: float = UNBROWSE_TIMEOUT_S
    unbrowse_corpus_threshold: float = UNBROWSE_CORPUS_THRESHOLD

    # Emission pool shares
    emission_traversal_share: float = EMISSION_TRAVERSAL_SHARE
    emission_quality_share: float = EMISSION_QUALITY_SHARE
    emission_topology_share: float = EMISSION_TOPOLOGY_SHARE

    # Node registration
    node_registration_enabled: bool = NODE_REGISTRATION_ENABLED
    pruning_enabled: bool = PRUNING_ENABLED
    pruning_epoch_interval: int = PRUNING_EPOCH_INTERVAL


# Commit-reveal (configured on-chain via btcli sudo set)
# CommitRevealWeightsEnabled = True
# CommitRevealPeriod = 1
