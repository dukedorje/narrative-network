"""Subnet configuration constants."""

from subnet import NETUID

# Scoring axis weights (must sum to 1.0)
TRAVERSAL_WEIGHT = 0.40
QUALITY_WEIGHT = 0.30
TOPOLOGY_WEIGHT = 0.15
CORPUS_WEIGHT = 0.15

# Traversal scoring
LATENCY_SOFT_LIMIT_S = 3.0
LATENCY_PENALTY_PER_S = 0.1
LATENCY_MAX_PENALTY = 0.5

# Quality scoring
MIN_HOP_WORDS = 100
MAX_HOP_WORDS = 500

# Topology scoring
BETWEENNESS_WEIGHT = 0.6
EDGE_WEIGHT_SUM_WEIGHT = 0.4
EDGE_WEIGHT_CAP = 50

# Graph store
EDGE_DECAY_RATE = 0.995
EDGE_DECAY_FLOOR = 0.01

# Validator
EPOCH_SLEEP_S = 60
MOVING_AVERAGE_ALPHA = 0.1
CHALLENGE_SAMPLE_SIZE = 10

# Commit-reveal (configured on-chain via btcli sudo set)
# CommitRevealWeightsEnabled = True
# CommitRevealPeriod = 1
