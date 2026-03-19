# Bittensor Knowledge Network — Quick Reference

## What's Working (✅)

Everything on the critical path is **fully implemented and tested**:

| Component | Status | Lines | Tests |
|-----------|--------|-------|-------|
| **Graph Store** | ✅ | 361 | betweenness, decay, traversal logs, BFS |
| **Validator** | ✅ | 287 | 4 scoring axes, fresh dendrite challenges, weight setting |
| **Emissions** | ✅ | 178 | 3 pools, corpus gate, normalization |
| **Reward Functions** | ✅ | 119 | traversal, quality, topology, corpus |
| **Seed Topology** | ✅ | 400 | 16 nodes, fully connected, corpus mapping |
| **Test Infrastructure** | ✅ | 239 | Full Bittensor mock layer, 6 fixtures |

## Key Files

### Core Implementation
- **Graph Store:** `/subnet/graph_store.py` — In-memory graph + optional KuzuDB, betweenness centrality, edge decay
- **Validator:** `/subnet/validator.py` — `run_epoch()` complete: corpus challenges, 4 scoring axes, weight setting
- **Emissions:** `/subnet/emissions.py` — TraversalPool (linear), QualityPool (softmax), TopologyPool (rank)
- **Rewards:** `/subnet/reward.py` — `score_traversal()`, `score_quality()`, `score_topology()`, `score_corpus()`
- **Config:** `/subnet/config.py` — All tunable constants, env-var override via `AXON_<KEY>`

### Seed Data
- **Topology:** `/seed/topology.yaml` — 16 nodes (quantum + 12 other domains), fully connected
- **Loader:** `/seed/loader.py` — Load YAML into GraphStore, resolve corpus files

### Testing
- **Fixtures:** `/tests/conftest.py` — MockSubtensor, MockWallet, MockDendrite, MockMetagraph, FakeEmbedder
- **Integration:** `/tests/test_integration.py` — Full epoch cycle validation

## Validator Epoch Loop (run_epoch)

```python
1. Resync metagraph
   → detect miner churn, grow score tensor

2. Select UIDs to challenge
   → sample N miners where is_serving=True

3. Corpus challenges
   → send KnowledgeQuery("__corpus_challenge__")
   → validate Merkle proofs
   → score_corpus(merkle_root_matches=True|False)

4. Traversal + Quality scoring
   → send KnowledgeQuery(query_text, query_embedding, top_k=5)
   → collect chunks from each miner
   → send NarrativeHop with chunks
   → score_traversal() + score_quality() on live responses

5. Topology scoring
   → use graph_store.betweenness_centrality(node_id)
   → use graph_store.outgoing_edge_weight_sum(node_id)
   → score_topology()

6. Aggregate via EmissionCalculator
   → build MinerScoreSnapshot per miner (4 scores + traversal count)
   → compute() → normalized weights via 3 pools + corpus gate

7. Update scores & set weights
   → scatter rewards into score tensor (moving average)
   → call subtensor.set_weights() → Bittensor chain

8. Edge decay
   → graph_store.decay_edges()
   → weight *= 0.995, floor at 0.01
```

## Scoring Axes (Sum = 1.0)

| Axis | Weight | Formula | Purpose |
|------|--------|---------|---------|
| **Traversal** | 0.40 | chunk_relevance + groundedness - latency_penalty | High-traffic, responsive miners |
| **Quality** | 0.30 | path_coherence + directional_progress + length_score | Narrative quality, coherence |
| **Topology** | 0.15 | 0.6 * betweenness + 0.4 * log(edge_weight) | Structural importance (bridges) |
| **Corpus** | 0.15 | 1.0\|0.3\|0.0 (Merkle gate) | Integrity check → fraud detection |

## Emissions Pools

| Pool | Normalization | Use Case |
|------|---------------|----------|
| **Traversal** | Linear | Proportional reward: traversal_score * traversal_count / sum |
| **Quality** | Softmax | Competitive: encourages quality arms race |
| **Topology** | Rank | Structural: reward bridge nodes regardless of traffic |

**Corpus Gate:** If `corpus_score == 0.0`, miner's emission → `1e-6` → eventual deregistration via Yuma Consensus.

## Configuration (via AXON_* env vars)

```bash
# Scoring weights
AXON_TRAVERSAL_WEIGHT=0.40
AXON_QUALITY_WEIGHT=0.30
AXON_TOPOLOGY_WEIGHT=0.15
AXON_CORPUS_WEIGHT=0.15

# Graph decay
AXON_EDGE_DECAY_RATE=0.995        # 0.5% loss per epoch
AXON_EDGE_DECAY_FLOOR=0.01

# Validator
AXON_EPOCH_SLEEP_S=60
AXON_MOVING_AVERAGE_ALPHA=0.1     # Score EMA weighting
AXON_CHALLENGE_SAMPLE_SIZE=10     # Miners per epoch

# Quality scoring
AXON_MIN_HOP_WORDS=100
AXON_MAX_HOP_WORDS=500

# Latency penalty
AXON_LATENCY_SOFT_LIMIT_S=3.0
AXON_LATENCY_PENALTY_PER_S=0.1
AXON_LATENCY_MAX_PENALTY=0.5
```

## Seed Topology

**16 nodes, fully connected:**

### Quantum Mechanics (4 sub-nodes)
- `quantum-foundations` — Wave functions, superposition, uncertainty (corpus: 3 files)
- `quantum-phenomena` — Double slit, tunneling, entanglement (corpus: 3 files)
- `quantum-interpretations` — Copenhagen, many-worlds, decoherence (corpus: 3 files)
- `quantum-bridge` — Spin, angular momentum (corpus: 1 file, bridge node)

### Other Domains (1 node each)
- relativity, thermodynamics, chemical-bonding, reaction-kinetics, phase-transitions, catalysis, polymers, biochemistry, ecology, climate-systems, evolutionary-biology

**Load:** 
```python
from seed.loader import load_topology
graph_store, corpus_map = load_topology()
print(graph_store.stats())  
# {'node_count': 16, 'edge_count': 240, 'live_nodes': 16, 'traversal_log_count': 0}
```

## Test Infrastructure

### Mock Layer (Complete Bittensor Stubs)

- **MockMetagraph** — hotkeys, uids, stakes, validator_permit, axons (is_serving)
- **MockWallet** — hotkey.ss58_address matching metagraph entry
- **MockSubtensor** — metagraph(netuid) + set_weights() with call logging
- **MockDendrite** — register_handler(synapse_type, fn) → dispatch KnowledgeQuery/NarrativeHop
- **FakeEmbedder** — Deterministic 768-dim vectors from text hash (no model download)

### Fixtures (conftest.py)

```python
@pytest.fixture def mock_metagraph()     # 4 nodes: 1 validator, 3 miners
@pytest.fixture def mock_wallet()        # Hotkey matches UID 0
@pytest.fixture def mock_subtensor()     # Returns metagraph, logs set_weights
@pytest.fixture def mock_dendrite()      # Routes synapses to handlers
@pytest.fixture def fake_embedder()      # Deterministic vectors
@pytest.fixture def graph_store()        # In-memory GraphStore(db_path=None)
```

### Run Tests

```bash
uv run pytest                                  # All
uv run pytest tests/test_integration.py -v    # Integration
uv run pytest tests/test_validator.py -v      # Validator unit
```

## Graph Algorithms

### Brandes Betweenness Centrality
- Unweighted shortest-path-based importance
- Returns dict: `{node_id: float [0, 1]}`
- Used for topology scoring (reward bridge nodes)
- Normalized: `cb[v] *= 1 / ((n-1)(n-2))`

### BFS Path Finding
- Returns shortest path or None
- Used for cycle detection, traversal auditing

## Zero Known Blockers

✅ All critical components fully implemented
✅ All scoring axes wired together
✅ Test infrastructure complete
✅ Seed topology loaded and mapped
✅ Validator `run_epoch()` has zero TODO stubs
✅ Configuration fully parameterizable

## Next Steps (If Needed)

1. **Testnet validation** — Deploy to Bittensor testnet, validate mock fidelity (deferred)
2. **Evolution integration** — Wire proposal/voting/pruning into lifecycle (separate subsystem)
3. **Observable metrics** — Add prometheus endpoints (operational)
4. **Performance tuning** — Profile betweenness on large graphs if needed

---

**See EXPLORATION_SUMMARY.md for detailed architecture, design decisions, and ADR.**
