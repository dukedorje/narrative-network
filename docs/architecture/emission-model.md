# Emission Model

This document specifies how Bittensor Knowledge Network (BKN) uses its validator weight-setting to distribute miner emissions. Under Dynamic TAO (dTAO), the protocol enforces a fixed emission split — our role is to set weights that direct the miner share toward the behaviors we want to incentivize.

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

## Weight-Setting Strategy: Three Emission Pools

The validator's `EmissionCalculator` (`subnet/emissions.py`) combines three pools into the final weight vector submitted to Yuma Consensus via `set_weights()`. The pools use different normalization strategies to suit the behavior they incentivize:

| Pool | Share | Normalization | What it rewards |
|------|-------|---------------|-----------------|
| TraversalPool | 50% | Linear (sum-normalized) | High-traffic, high-relevance nodes |
| QualityPool | 30% | Softmax | Competitive narrative quality |
| TopologyPool | 20% | Rank-based | Structural bridge importance |

```python
# From subnet/emissions.py — EmissionCalculator.compute()
score = (
    traversal_share * t_weights[i]   # 0.50
    + quality_share * q_weights[i]   # 0.30
    + topology_share * top_weights[i] # 0.20
)
# Corpus gate: zero corpus score collapses weight to near-zero
if snap.corpus_score == 0.0:
    score = 1e-6
```

The final combined scores are L1-normalized before being passed to `set_weights()`.

---

## Corpus Score: A Gate, Not a Pool

Corpus integrity is **not** a fourth emission pool. It is a binary gate applied after pool combination:

- `corpus_score == 0.0` → miner's combined weight is floored to `1e-6` (near-zero emission → eventual deregistration)
- `corpus_score > 0.0` → no effect on combined weight; the miner competes normally across all three pools

This means corpus fraud has an outsized punishment: it zeroes out emission regardless of how well a miner performs on traversal, quality, or topology. There is no partial credit pathway that lets a fraudulent miner survive.

---

## The Four Scoring Axes (reward.py)

The four axes in `subnet/reward.py` describe how **raw scores are computed per miner per hop**. They are the inputs to the emission system, not the emission system itself:

| Axis | Described weight | Purpose | Used in |
|------|-----------------|---------|---------|
| Traversal quality | 0.40 | Chunk relevance + passage groundedness + latency | TraversalPool input |
| Narrative quality | 0.30 | Path coherence + directional progress + length | QualityPool input |
| Topology importance | 0.15 | Betweenness centrality + edge weight sum | TopologyPool input |
| Corpus integrity | 0.15 | Merkle root stability | Corpus gate |

The 0.40/0.30/0.15/0.15 weights in `reward.py` describe the **sub-score composition within each axis**. They do not directly set emission pool shares. Pool shares (50%/30%/20%) are configured separately in `subnet/config.py` as `EMISSION_TRAVERSAL_SHARE`, `EMISSION_QUALITY_SHARE`, and `EMISSION_TOPOLOGY_SHARE`.

### Validator Scoring Loop

The scoring loop in `subnet/validator.py` that calls `reward.py` and feeds `EmissionCalculator` is currently a skeleton (TODO). The pool and gate architecture is implemented and tested; wiring the live scoring loop to `set_weights()` is Phase 1 MVP work.

---

## TraversalPool (50%)

Rewards miners with high traversal traffic weighted by relevance score.

```python
# From subnet/emissions.py — TraversalPool.weights()
raw = [s.traversal_score * max(s.traversal_count, 1) for s in snapshots]
return _linear_normalise(raw)  # divide each by total sum
```

Linear normalization means rewards scale proportionally with both quality (traversal_score) and volume (traversal_count). A miner improving average score from 0.65 to 0.80 on a well-traversed node earns significantly more than the absolute score increase suggests — quality and traffic compound.

Raw traversal scores are computed in `reward.py → score_traversal()`:
```python
chunk_relevance = cosine_similarity(chunks_embedding, query_embedding)
groundedness = cosine_similarity(passage_embedding, domain_centroid)
latency_excess = max(0.0, process_time - LATENCY_SOFT_LIMIT_S)
penalty = min(latency_excess * LATENCY_PENALTY_PER_S, LATENCY_MAX_PENALTY)
raw = 0.6 * chunk_relevance + 0.4 * groundedness
return max(0.0, raw * (1.0 - penalty))
```

---

## QualityPool (30%)

Rewards miners producing high-quality narrative passages, using softmax to sharpen competition.

```python
# From subnet/emissions.py — QualityPool.weights()
return _softmax([s.quality_score for s in snapshots])
```

Softmax amplifies differences between miners: a miner with score 0.8 earns substantially more than one with 0.7, creating sharp competitive pressure at the top of the quality distribution.

Raw quality scores are computed in `reward.py → score_quality()`:
```python
return 0.4 * path_coherence + 0.3 * directional_progress + 0.3 * length_score
```

Comparative scoring: multiple miners respond to the same `NarrativeHop`. The best passage wins not because it matches a correct answer but because it best serves the traversal path relative to competitors.

---

## TopologyPool (20%)

Rewards miners whose nodes are structurally important as bridges, independent of current traffic volume.

```python
# From subnet/emissions.py — TopologyPool.weights()
return _rank_normalise([s.topology_score for s in snapshots])
```

Rank normalization (not linear) means relative ordering matters, not absolute score magnitude. This prevents a single dominant hub from claiming the entire topology allocation.

Raw topology scores are computed in `reward.py → score_topology()`:
```python
bc = min(betweenness_centrality, 1.0)
ew = min(math.log1p(outgoing_edge_weight_sum) / math.log1p(EDGE_WEIGHT_CAP), 1.0)
return BETWEENNESS_WEIGHT * bc + EDGE_WEIGHT_SUM_WEIGHT * ew
```

- **Betweenness centrality** — rewards miners whose nodes bridge distinct clusters (Brandes O(VE))
- **Outgoing edge weight sum** — soft-capped via `log1p` to prevent saturation

Key property: newly integrated bridge nodes earn meaningful topology scores from day one, before traffic discovery. This gives new entrants a viable strategy: extend the graph into underserved regions rather than competing head-to-head with established hubs.

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

The corpus gate (`corpus_score == 0.0 → 1e-6`) is the primary enforcement mechanism for corpus fraud. It overrides all pool scores and is sufficient for: corpus fraud, quality drops, semantic drift, inactivity.

### 2. Bond Forfeiture (Off-Chain / Alkahest)

For proposal bonds, the owner manages bond lifecycle:
- Bonds locked via Alkahest escrow on its existing L2
- Validator quorum acts as arbiter for release/forfeit decisions
- Forfeited bonds retained by owner (not slashed on-chain)

This is sufficient for: proposal spam, failed incubation, manifest fraud.

---

## Validator Earnings

Validators earn from the protocol's 41% validator+staker share, **not** from a custom emission pool. Their earnings are determined by:

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

Popular hubs earn more from the TraversalPool (linear normalization rewards volume × quality). Structurally important bridges earn more from TopologyPool (rank normalization, independent of traffic). The two pools hedge each other: established hubs dominate traversal, new bridge nodes dominate topology.

### 2. Quality compounding

Higher scores → more emission → better hardware → higher quality → more wins. This convexity is intentional. Softmax in QualityPool sharpens this effect at the top of the distribution. The network rewards quality escalation, not just participation.

### 3. New entrant strategy

New miners cannot beat established hubs on quality immediately. But they can extend the graph into underserved regions, earning topology rewards that fund infrastructure for eventual quality competition.

### 4. Single unified weight vector

All miner emission flows through a single weight vector submitted to Yuma Consensus. The three pools shape how that vector is computed, but the distribution mechanism is unified — Yuma Consensus handles aggregation across validators.

---

## Configuration Reference

| Parameter | Description | Default |
|-----------|-------------|---------|
| `EMISSION_TRAVERSAL_SHARE` | TraversalPool fraction | 0.50 |
| `EMISSION_QUALITY_SHARE` | QualityPool fraction | 0.30 |
| `EMISSION_TOPOLOGY_SHARE` | TopologyPool fraction | 0.20 |
| `LATENCY_SOFT_LIMIT_S` | Seconds before latency penalty | 3.0 |
| `LATENCY_PENALTY_PER_S` | Penalty per excess second | 0.1 |
| `LATENCY_MAX_PENALTY` | Maximum latency penalty | 0.5 |
| `MIN_HOP_WORDS` | Minimum passage word count | 100 |
| `MAX_HOP_WORDS` | Maximum passage word count | 500 |
| `BETWEENNESS_WEIGHT` | Betweenness centrality weight in topology score | 0.6 |
| `EDGE_WEIGHT_SUM_WEIGHT` | Edge weight sum contribution in topology score | 0.4 |
| `EDGE_WEIGHT_CAP` | log1p cap for edge weight normalization | 50 |
