# Evolution Model C: Miner-Owned Nodes with Quality-Determined Survival

## Overview

Model C is the current operational model for Bittensor Knowledge Network (BKN) subnet 42. Miners own knowledge-domain nodes. A node's survival is determined entirely by quality — validators score miners on traversal relevance, narrative quality, topology importance, and corpus integrity, then prune underperforming nodes through a three-phase state machine.

There is no on-chain governance for node proposals or admission in Model C. That is deferred to future work (see [What Comes Later](#what-comes-later)). Instead, registration is a lightweight commit-reveal: a miner stakes TAO and publishes a `DomainManifest`, then commits the manifest CID on-chain via `subtensor.set_commitment()`. The validator reads the CID, loads the manifest from local store, and registers the node.

---

## Node Lifecycle

```
Registration
    |
    v
  Live  <----------- recovery (score recovers)
    |
    | score < warning_threshold (default 0.35)
    v
 WARNING
    |
    | score < decay_threshold (default 0.20)
    v
 DECAYING
    |
    | consecutive_below >= collapse_consecutive (default 24 epochs)
    v
COLLAPSED  -> graph_store.set_node_state("Pruned")
```

### Registration

A miner registers by:

1. Constructing a `DomainManifest` (see `domain/manifest.py`) with fields including `node_id`, `domain`, `narrative_persona`, `adjacent_nodes`, `corpus_root_hash`, and `miner_hotkey`.
2. Saving the manifest to a local `ManifestStore`, which content-hashes the JSON and returns a CID.
3. Committing the CID on-chain: `subtensor.set_commitment(netuid, uid, cid)`.

The validator, in `_register_manifests()`, reads CIDs from serving UIDs, loads manifests from local store, and calls `graph_store.add_node(node_id, state="Live")`. The UID-to-node-ID mapping is stored in `validator._uid_to_node_id`.

**Cold-start topology penalty**: New nodes have zero betweenness centrality and zero outgoing edge weight. This is intentional — miners must earn traversals to gain topology score. The topology pool (25% of emissions) rewards nodes that become well-connected through quality performance. No nursery bonus or integration ramp exists in Model C. Future work may introduce one (see [What Comes Later](#what-comes-later)).

### Scoring Axes

Each epoch the validator challenges miners on four axes (see `subnet/reward.py`):

| Axis | Pool Share | Description |
|---|---|---|
| Traversal | 40% | Cosine similarity between query embedding and returned chunks |
| Quality | 35% | Semantic coherence of narrative passage; penalised by choice card fairness |
| Topology | 25% | Betweenness centrality + outgoing edge weight sum |
| Corpus | gate | Merkle proof validity; gates traversal/quality scores for corpus miners |

Corpus integrity is a gate, not a pool. A miner with an invalid or inconsistent Merkle root receives `corpus_score=0`, which gates their traversal and quality rewards. Corpus integrity does not draw from an emission pool of its own.

### Pruning: Three-Phase State Machine

The `PruningEngine` (`evolution/pruning.py`) maintains a rolling score window and phase per node:

- **HEALTHY**: mean score >= `warning_threshold` (0.35). Normal operation.
- **WARNING**: mean score in [decay_threshold, warning_threshold). Quality is degrading but not yet critical.
- **DECAYING**: mean score < `decay_threshold` (0.20). Edge decay is applied aggressively; node risks collapse.
- **COLLAPSED**: consecutive epochs below decay_threshold >= `collapse_consecutive` (default 24). The validator calls `graph_store.set_node_state(node_id, "Pruned")`. The node is removed from the live graph.

The engine is called every `PRUNING_EPOCH_INTERVAL` epochs (default 10). Nodes that have insufficient traversals over the rolling window (`traversals < min_traversals`) are also auto-collapsed regardless of score.

Phase transitions are one-way toward collapse, except recovery: if mean score recovers above `warning_threshold`, the node returns to HEALTHY from any non-COLLAPSED phase.

---

## Edge Dynamics

Edges in the knowledge graph represent traversal paths between domains. They are:

- **Formed** when the validator calls `graph_store.reinforce_edge(source, dest, quality_score)` after a scored hop.
- **Reinforced** with each subsequent traversal through the same path: `edge.weight += quality_score`, capped at `EDGE_DECAY_FLOOR * 1000`.
- **Decayed** multiplicatively each epoch: `edge.weight *= EDGE_DECAY_RATE` (default 0.95), floored at `EDGE_DECAY_FLOOR`. Edges at the floor are deleted.

This means high-quality paths persist and grow; paths that are scored poorly or rarely traversed decay and disappear. The topology score for a node is proportional to its betweenness centrality (how often it appears on shortest paths) and its outgoing edge weight sum.

New miners start with no edges and therefore zero topology score. They must generate quality corpus responses and narrative passages to attract traversals and build edge weight.

---

## Knowledge Sync (Stub)

`domain/knowledge_sync.py` implements `KnowledgeSyncGate`, a cosine-distance gate for nearby-node corpus sharing. When two nodes are semantically close (centroid distance below threshold), they may optionally share corpus chunks.

**Current state**: This is a stub. The gate logic exists but is not wired into the validator epoch loop. It is included as infrastructure for a future feature where miners in adjacent domains can bootstrap from each other's corpora, reducing cold-start data requirements.

---

## Graph Divergence

Different validators intentionally maintain divergent graphs. There is no synchronization protocol in Model C. Divergence occurs because:

1. Each validator independently challenges a random sample of miners each epoch.
2. Each validator independently reinforces edges based on its own traversal sessions.
3. Edge decay and pruning are applied locally by each validator.

This is not a bug. It creates a naturally diverse view of the knowledge network, where validators with different traversal histories develop different topology weights. Consensus on miner quality emerges through Yuma Consensus on weight vectors, not through graph synchronization.

**Eventual consistency via Bonfires**: Future work will push graph state to a centralized Bonfires TNT v2 API, providing eventual consistency across validators. This is noted in `subnet/graph_store.py` as a `# FUTURE` comment. Bonfires sync is explicitly out of scope for Model C.

---

## Emission Pool Economics

Current emission pool split (see `subnet/config.py`):

| Pool | Share | Rationale |
|---|---|---|
| Traversal | 40% | Rewards miners whose corpus is most relevant to validator queries — the core function of a knowledge node |
| Quality | 35% | Rewards narrative coherence and passage depth — what makes the network compelling to players |
| Topology | 25% | Rewards structural importance in the graph — incentivizes well-connected, frequently-traversed nodes |

The traversal pool is the largest because corpus relevance is the primary capability being incentivized. A miner that cannot retrieve relevant chunks provides no value regardless of narrative quality. The quality pool is significant because narrative generation is the differentiating skill in a competitive multi-miner environment. Topology rewards are smaller because centrality is an emergent property of the other two axes — it cannot be directly optimized without also being a good traversal and quality miner.

**Choice card fairness**: Miners that omit adjacent nodes from their choice cards receive a quality score multiplier < 1.0. This penalizes traffic-steering attacks where miners attempt to funnel all traversals to their node by not offering competing paths.

**EmissionCalculator** (`subnet/emissions.py`) normalizes scores within each pool (rank/linear/softmax) and produces a final weight vector submitted via `subtensor.set_weights()`.

---

## What Comes Later

These capabilities are explicitly out of scope for Model C and are deferred to future model revisions:

### Model A/B: Proposal and Voting Governance
On-chain proposal submission, stake-weighted voting with quorum and approval threshold, node bonding, and the `evolution/proposal.py` + `evolution/voting.py` infrastructure. Model C skips this and allows direct registration, trading governance security for simplicity during early subnet development.

### Comparative Attestation
Head-to-head miner comparison where multiple miners compete on the same hop and validators compare passage quality directly. The validator's `run_epoch()` includes a `# FUTURE: Comparative attestation` comment. This requires a different synapse design and a pairwise scoring function.

### LLM Adversarial Controls
Detection and penalization of narrative gaming — miners that generate high-cosine-similarity passages without genuine semantic content, or that exploit scoring functions. Noted as `# FUTURE: LLM adversarial controls` in `validator.py`.

### Bonfires Centralized DB Sync
Push graph state to Bonfires TNT v2 API for cross-validator eventual consistency. See `graph_store.py` `# FUTURE` comment. Enables a globally-consistent view of the knowledge network while preserving local divergence during normal operation.

### Node Integration Ramp / Nursery Bonus
A grace period for newly registered nodes, providing a small topology bonus during the first N epochs to counteract the cold-start penalty. The `evolution/integration.py` FORESHADOW → BRIDGE → LIVE integration phases are implemented but not wired into Model C's validator epoch loop.

### Full Economic Analysis
Formal modeling of emission pool parameters (40/35/25 split), decay rates, pruning thresholds, and their interactions with miner strategy. Current constants are informed by intuition and preliminary testing; formal analysis with equilibrium modeling is deferred.

### NLA Settlement
On-collapse NLA bond burn via `NLASettlementClient`. The `PruningEngine._settle_collapse_nla()` method is implemented but `nla_client=None` is passed in both `Validator` and `LocalValidator`, making it a no-op in Model C. Wiring requires a live NLA endpoint and bond registration flow.
