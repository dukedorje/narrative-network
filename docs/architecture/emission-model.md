# Emission Model

This document specifies how Narrative Network (Bittensor subnet 42) uses its validator weight-setting to distribute miner emissions. Under Dynamic TAO (dTAO), the protocol enforces a fixed emission split — our role is to set weights that direct the miner share toward the behaviors we want to incentivize.

---

## Protocol-Enforced Emission Split (dTAO)

The Bittensor protocol distributes each subnet's emission per tempo as follows:

| Recipient | Share | Our Control |
|-----------|-------|-------------|
| Subnet Owner | 18% | Fixed by protocol. Funds operations, proposal reserve, development. |
| Miners | 41% | Distributed by Yuma Consensus based on **our validator weight assignments**. |
| Validators + Stakers | 41% | Distributed by bond/dividend mechanism. Validators earn by setting accurate weights. |

**We do not control the split.** We control how the 41% miner share is distributed among miners by setting weights. The weights we assign are the emission model.

---

## Weight-Setting Strategy: Four Scoring Axes

Our validators compute a combined score per miner UID. This score becomes the weight set via `subtensor.set_weights()`. The four axes determine how the 41% miner emission is distributed:

| Axis | Weight | Purpose | Equivalent to |
|------|--------|---------|---------------|
| Traversal quality | 0.40 | Reward relevant chunk retrieval and passage groundedness | Traversal pool |
| Narrative quality | 0.30 | Reward coherent, well-synthesized narrative passages | Quality bonus |
| Topology importance | 0.15 | Reward structurally important bridge nodes | Topology pool |
| Corpus integrity | 0.15 | Penalize inconsistent or fraudulent corpora | Integrity enforcement |

```python
final_weight = (
    0.40 * traversal_score +
    0.30 * quality_score +
    0.15 * topology_score +
    0.15 * corpus_score
)
```

Within each axis, domain miners and narrative miners compete for the same weight allocation. The scoring naturally favors the miner type doing the relevant work:

- **Traversal quality**: Domain miners score higher (they serve the chunks being evaluated)
- **Narrative quality**: Narrative miners score higher (they generate the passages)
- **Topology importance**: Both benefit equally from structural position
- **Corpus integrity**: Domain miners are primarily affected (they commit Merkle roots)

### mechid Consideration

SDK v10 supports `mechid` — subnets can run up to 2 independent incentive mechanisms. We may use:
- `mechid=0`: Combined scoring (default, described above)
- `mechid=1`: Future — separate narrative-only scoring track

For MVP, a single mechanism (`mechid=0`) with the combined four-axis score is sufficient.

---

## Traversal Quality (weight: 0.40)

Measures how relevant the miner's contribution is to the actual traversal.

For each completed `NarrativeHop` in an epoch, validators score:
- Cosine similarity between returned chunks and query embedding
- Passage groundedness against retrieved chunks
- Latency penalty beyond soft limit

```python
def score_traversal(response, hop_context):
    chunk_relevance = cosine_similarity(response.chunks, hop_context.query_embedding)
    groundedness = cosine_similarity(response.passage_embedding, hop_context.domain_centroid)

    # Latency penalty
    latency_excess = max(0, response.process_time - LATENCY_SOFT_LIMIT_S)
    penalty = min(latency_excess * LATENCY_PENALTY_PER_S, LATENCY_MAX_PENALTY)

    raw = 0.6 * chunk_relevance + 0.4 * groundedness
    return raw * (1 - penalty)
```

Key insight: quality-weighting inside traversal scoring means high-quality nodes on high-traffic paths compound rewards. A miner improving average score from 0.65 to 0.80 on a well-traversed node earns significantly more than the absolute score increase suggests.

---

## Narrative Quality (weight: 0.30)

Measures passage coherence, synthesis quality, and narrative continuity.

```python
def score_quality(response, hop_context):
    # Coherence: does the passage connect to the path so far?
    path_coherence = cosine_similarity(
        response.passage_embedding,
        mean(hop_context.path_embeddings)
    )

    # Direction: does it move toward the destination domain?
    directional_progress = cosine_similarity(
        response.passage_embedding,
        hop_context.destination_centroid
    ) - cosine_similarity(
        response.passage_embedding,
        hop_context.source_centroid
    )

    # Word count heuristic (MVP; replaced by embedding scoring later)
    word_count = len(response.narrative_passage.split())
    length_score = 1.0 if MIN_HOP_WORDS <= word_count <= MAX_HOP_WORDS else 0.4

    return 0.4 * path_coherence + 0.3 * max(0, directional_progress) + 0.3 * length_score
```

Comparative scoring: multiple miners respond to the same `NarrativeHop`. Validators rank them comparatively — no ground truth needed. The best passage wins not because it matches a correct answer but because it best serves the attractor basin relative to competitors.

---

## Topology Importance (weight: 0.15)

Derived from the validator's local graph store. Measures structural importance independent of current traffic volume.

```python
def score_topology(node_id, graph_store):
    centrality = graph_store.betweenness_centrality(node_id)  # Brandes O(VE)
    edge_weight_sum = graph_store.outgoing_edge_weight_sum(node_id)

    return (
        0.6 * min(centrality, 1.0) +
        0.4 * min(log1p(edge_weight_sum) / log1p(50), 1.0)
    )
```

- **Betweenness centrality** (60%) — rewards miners whose nodes bridge distinct clusters
- **Outgoing edge weight sum** (40%) — soft-capped via `log1p` to prevent saturation

Key property: newly integrated bridge nodes earn meaningful topology scores from day one, before traffic discovery. This gives new entrants a viable strategy: extend the graph into underserved regions rather than competing head-to-head with established hubs.

---

## Corpus Integrity (weight: 0.15)

Verifies that domain miners serve consistent, honest corpora.

```python
def score_corpus(miner_uid, challenge_result):
    if challenge_result.merkle_root_matches:
        return 1.0   # consistent corpus
    elif challenge_result.partial_match:
        return 0.3   # some chunks changed (may indicate legitimate update)
    else:
        return 0.0   # fraud or severe inconsistency
```

A score of 0.0 here means the miner receives near-zero overall weight → zero emission → eventual deregistration. This is the primary enforcement mechanism (see "Penalty Mechanics" below).

---

## Owner Revenue as Proposal Reserve

The protocol's 18% owner share replaces our original "proposal reserve" concept. This revenue stream funds:

| Use | Description |
|-----|-------------|
| Proposal bond returns | Successful proposals get bond × 1.05 from owner funds |
| Operations | Infrastructure, development, maintenance |
| Governance | Community initiatives, ecosystem grants |
| Lapsed bond buffer | 95% of lapsed proposal bonds returned; 5% retained |

Bond lifecycle managed off-chain by the subnet owner, or optionally via Alkahest escrow on its existing L2 deployment:

| Outcome | Bond Disposition |
|---------|-----------------|
| Successful proposal (incubation passed) | Bond returned + 5% bonus from owner revenue |
| Lapsed proposal (insufficient quorum) | 95% of bond returned |
| Fraudulent proposal (corpus fraud detected) | Bond forfeited; retained by owner |

---

## Penalty Mechanics (No Native Slashing)

Bittensor has no protocol-level slashing. Our enforcement uses two mechanisms:

### 1. Weight-Based Penalty (Native)

Validators assign zero or near-zero weight to misbehaving miners:
- Zero weight → zero emission from the 41% miner share
- Sustained zero emission → economic death
- Eventually replaced by new registrant (lowest-emission UID deregistered when slots are full)

This is sufficient for: corpus fraud, quality drops, semantic drift, inactivity.

### 2. Bond Forfeiture (Off-Chain / Alkahest)

For proposal bonds, the owner manages bond lifecycle:
- Bonds locked via Alkahest escrow on its existing L2
- Validator quorum acts as arbiter for release/forfeit decisions
- Forfeited bonds retained by owner (not slashed on-chain)

This is sufficient for: proposal spam, failed incubation, manifest fraud.

---

## Validator Earnings

Validators earn from the protocol's 41% validator+staker share, **not** from a custom "quality pool." Their earnings are determined by:

1. **Bond mechanism**: Yuma Consensus computes bonds based on how well validator weights align with consensus. Higher alignment → larger bond → larger dividend share.
2. **vtrust**: Sum of consensus-clipped weights. Validators with high vtrust earn proportionally more.
3. **Staker delegation**: Nominators stake to validators, increasing their consensus influence. Validators take a commission (default 18%).

Validators are incentivized to:
- Score honestly (consensus alignment maximizes dividends)
- Stay online (activity cutoff excludes inactive validators)
- Maintain graph infrastructure (required for accurate scoring)

---

## Subnet Economic Health Under dTAO

Our subnet's total emission depends on **net TAO staking inflows**. To attract and retain stakers:

1. **Demonstrate value**: Clear metrics showing traversal quality, knowledge graph growth, miner competition
2. **Alpha token appreciation**: As more TAO flows in, alpha price rises, benefiting existing stakers
3. **Validator returns**: High-quality scoring → high vtrust → competitive validator dividends
4. **Bittensor Foundation support**: We may receive initial TAO tokens and help starting the subnet

Negative net flow = zero emissions = subnet death spiral. Staker confidence is existential.

---

## Key Economic Properties

### 1. Traffic concentration hedge

Popular hubs earn more from traversal quality weighting. Structurally important bridges earn more from topology scoring. The two axes hedge each other: established hubs dominate traversal, new bridge nodes dominate topology.

### 2. Quality compounding

Higher scores → more emission → better hardware → higher quality → more wins. This convexity is intentional. The network rewards quality escalation, not just participation.

### 3. New entrant strategy

New miners cannot beat established hubs on quality immediately. But they can extend the graph into underserved regions, earning topology rewards that fund infrastructure for eventual quality competition.

### 4. No separate "pools"

Unlike our original design, there are no separate token pools with independent distribution. All miner emission flows through a single weight vector. The "pools" are axis weights in the scoring function — they shape the weight vector, but the distribution mechanism is unified through Yuma Consensus.

---

## Configuration Reference

| Parameter | Description | Default |
|-----------|-------------|---------|
| `TRAVERSAL_WEIGHT` | Weight for traversal axis | 0.40 |
| `QUALITY_WEIGHT` | Weight for quality axis | 0.30 |
| `TOPOLOGY_WEIGHT` | Weight for topology axis | 0.15 |
| `CORPUS_WEIGHT` | Weight for corpus axis | 0.15 |
| `LATENCY_SOFT_LIMIT_S` | Seconds before latency penalty | 3.0 |
| `LATENCY_PENALTY_PER_S` | Penalty per excess second | 0.1 |
| `LATENCY_MAX_PENALTY` | Maximum latency penalty | 0.5 |
| `MIN_HOP_WORDS` | Minimum passage word count | 100 |
| `MAX_HOP_WORDS` | Maximum passage word count | 500 |
