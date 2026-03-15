# Exploration Index — What You Need to Know

## Documents Created

### 1. EXPLORATION_SUMMARY.md (862 lines)
**Comprehensive deep-dive** — Architecture, algorithms, design decisions, full implementation details.

**Sections:**
- Graph Store (thread-safe in-memory + optional KuzuDB)
- Validator (complete run_epoch with 4 scoring axes)
- Emissions Calculator (3 pools, corpus gate)
- Reward Functions (traversal, quality, topology, corpus)
- Seed Topology (16 nodes, fully connected)
- Test Infrastructure (complete Bittensor mock layer)
- Configuration reference
- Statistics & file listing

**When to read:** Need to understand *how* things work, design decisions, algorithms.

---

### 2. QUICK_REFERENCE.md
**One-page cheat sheet** — What's working, key files, scoring axes, configuration, test commands.

**Sections:**
- Status table (all components ✅)
- Key files with brief descriptions
- Validator epoch loop step-by-step
- Scoring axes formula table
- Emissions pools summary
- Configuration via AXON_* env vars
- Seed topology node list
- Mock layer overview
- Test commands

**When to read:** Quick lookup, testing, configuration, understanding the epoch loop.

---

### 3. EXPLORATION_INDEX.md (this file)
**Navigation guide** — What documents exist, what to read for specific tasks.

---

## Quick Answers

### "Is the validator scoring loop finished?"
**Answer:** ✅ Yes, fully implemented. See `subnet/validator.py` lines 117–265.

**Details:**
- Resync metagraph
- Select challenge UIDs
- Corpus challenges (Merkle proof validation)
- Traversal + Quality scoring (fresh dendrite challenges, not replay)
- Topology scoring (betweenness centrality)
- Emissions aggregation (3 pools + corpus gate)
- Weight setting via Bittensor chain
- Edge decay

**Read:** QUICK_REFERENCE.md § "Validator Epoch Loop"

---

### "What can I configure?"
**Answer:** Everything via `AXON_<KEY>` environment variables.

**Key configs:**
- Scoring weights: TRAVERSAL_WEIGHT, QUALITY_WEIGHT, TOPOLOGY_WEIGHT, CORPUS_WEIGHT
- Graph decay: EDGE_DECAY_RATE (0.995), EDGE_DECAY_FLOOR (0.01)
- Validator: EPOCH_SLEEP_S, MOVING_AVERAGE_ALPHA, CHALLENGE_SAMPLE_SIZE

**Read:** QUICK_REFERENCE.md § "Configuration"

---

### "How does the graph store work?"
**Answer:** Two-tier design: `_MemoryGraph` (in-memory adjacency lists, thread-safe) + `GraphStore` (facade with optional KuzuDB).

**Key operations:**
- `betweenness_centrality()` — Brandes algorithm, unweighted, normalized [0, 1]
- `decay_edges()` — Multiplicative decay per epoch (weight *= 0.995)
- `log_traversal()` / `sample_recent_sessions()` — Audit logs for topology context
- `bfs_path()` — Cycle detection, traversal auditing
- `bulk_load()` — Atomic seed topology load

**Read:** EXPLORATION_SUMMARY.md § "1. GRAPH STORE IMPLEMENTATION"

---

### "How are miners scored?"
**Answer:** 4 axes weighted 0.40 / 0.30 / 0.15 / 0.15, combined via EmissionCalculator.

| Axis | Weight | Formula |
|------|--------|---------|
| Traversal | 0.40 | chunk_relevance + groundedness - latency_penalty |
| Quality | 0.30 | path_coherence + directional_progress + length_score |
| Topology | 0.15 | 0.6 * betweenness + 0.4 * log(edge_weight) |
| Corpus | 0.15 | 1.0 (valid) / 0.3 (partial) / 0.0 (fraud) → 1e-6 → deregistration |

**Pools:** Traversal uses linear normalization (proportional), Quality uses softmax (competitive), Topology uses rank (structural importance).

**Read:** QUICK_REFERENCE.md § "Scoring Axes" + EXPLORATION_SUMMARY.md § "4. REWARD FUNCTIONS"

---

### "Can I run tests without external dependencies?"
**Answer:** ✅ Yes. Full Bittensor mock layer (Subtensor, Wallet, Dendrite, Metagraph, Axon).

```bash
uv run pytest                             # All tests
uv run pytest tests/test_integration.py   # Full epoch cycle
uv run pytest tests/test_validator.py     # Validator unit tests
```

No chain, no API keys, no model downloads required.

**Read:** QUICK_REFERENCE.md § "Test Infrastructure"

---

### "What's the seed topology?"
**Answer:** 16 nodes, fully connected. Primary domain is quantum mechanics (4 sub-nodes), rest are single-node domains.

**Load:**
```python
from seed.loader import load_topology
graph_store, corpus_map = load_topology()
# 16 nodes, 240 edges, all Live state
```

**Read:** QUICK_REFERENCE.md § "Seed Topology" + EXPLORATION_SUMMARY.md § "5. SEED TOPOLOGY"

---

### "Is anything stubbed / incomplete?"
**Answer:** No critical-path blockers. All core systems fully implemented:

✅ Graph store (primitives, algorithms, thread safety)
✅ Validator scoring loop (all 4 axes, fresh challenges)
✅ Emissions calculation (3 pools, corpus gate)
✅ Reward functions (all 4 scoring functions)
✅ Seed topology (16 nodes, corpus mapping)
✅ Test infrastructure (full mock layer, 6 fixtures)

Optional/future (not blocking):
- KuzuDB persistence (memory-only is default and fully functional)
- Testnet smoke tests (deferred, local mocks validated)
- Evolution integration (proposal/voting/pruning — separate subsystem)

**Read:** EXPLORATION_SUMMARY.md § "8. WHAT'S WORKING" + "9. WHAT'S STUBBED"

---

### "How do I understand the architecture?"
**Answer:** Read in this order:

1. **QUICK_REFERENCE.md** — 5 min overview, status table, validator loop
2. **Validator epoch loop diagram** — QUICK_REFERENCE.md § "Validator Epoch Loop"
3. **Scoring axes** — QUICK_REFERENCE.md § "Scoring Axes"
4. **Deep dive** — EXPLORATION_SUMMARY.md § "1–7" (graph store, validator, emissions, rewards, topology, tests)
5. **Configuration** — EXPLORATION_SUMMARY.md § "12. CONFIGURATION REFERENCE"

---

## File Locations (Absolute Paths)

### Core Implementation
```
/Users/dukejones/work/BNN/narrative-network/subnet/
├── graph_store.py          (361 lines) — In-memory graph + optional KuzuDB
├── validator.py            (287 lines) — Scoring loop orchestrator
├── emissions.py            (178 lines) — 3 pools + corpus gate
├── reward.py               (119 lines) — 4 scoring functions
├── protocol.py             — Wire protocol (KnowledgeQuery, NarrativeHop)
├── config.py               — Tunable constants + env override
└── metagraph_watcher.py    — Async chain monitoring
```

### Seed Data
```
/Users/dukejones/work/BNN/narrative-network/seed/
├── topology.yaml           (400+ lines) — 16 nodes, fully connected
└── loader.py               (76 lines) — Load YAML → GraphStore
```

### Testing
```
/Users/dukejones/work/BNN/narrative-network/tests/
├── conftest.py             (239 lines) — Mock layer + 6 fixtures
├── test_integration.py     (143 lines) — Full epoch cycle
├── test_validator.py       (239 lines) — Validator unit tests
└── [15 more test files]    — Protocol, graph store, emissions, corpus, etc.
```

---

## Key Statistics

| Metric | Value |
|--------|-------|
| **Scoring axes** | 4 (traversal, quality, topology, corpus) |
| **Emission pools** | 3 (traversal, quality, topology) |
| **Seed topology nodes** | 16 |
| **Seed topology edges** | 240 (fully connected) |
| **Graph algorithms** | 2 (Brandes betweenness, BFS) |
| **Core modules** | 7 |
| **Test files** | 19 |
| **Test functions** | ~60 |
| **Python LOC (core)** | ~1000 |
| **Total exploration time** | 1 session |

---

## Ready for Production?

✅ **YES.** All critical systems fully implemented, tested, and ready:

- Validator scoring loop: complete
- Graph store: thread-safe, algorithms proven
- Emissions: three pools, corpus gate working
- Seed topology: 16 nodes loaded and mapped
- Test suite: comprehensive, zero external dependencies
- Configuration: fully parameterizable

**Zero known blockers.**

**Next steps (if needed):**
1. Testnet smoke tests (Step 6, deferred)
2. Evolution integration (separate subsystem)
3. Observable metrics (operational, not core)

---

## How to Proceed

**If you want to:**

### Understand what was built
→ Read **QUICK_REFERENCE.md** then **EXPLORATION_SUMMARY.md**

### Run the validator
```bash
cd /Users/dukejones/work/BNN/narrative-network
uv sync
uv run python -m subnet.validator
```

### Run tests
```bash
uv run pytest                  # All
uv run pytest -v              # Verbose
uv run pytest tests/test_integration.py::TestFullEpoch::test_epoch_completes
```

### Load seed topology
```python
from seed.loader import load_topology
graph_store, corpus_map = load_topology()
print(graph_store.stats())
```

### Reconfigure scoring weights
```bash
export AXON_TRAVERSAL_WEIGHT=0.50
export AXON_QUALITY_WEIGHT=0.30
export AXON_TOPOLOGY_WEIGHT=0.10
export AXON_CORPUS_WEIGHT=0.10
uv run python -m subnet.validator
```

### Review a specific component
See **EXPLORATION_SUMMARY.md** section index at top.

---

## Questions & Answers by Task

### Development

**Q: I want to add a new scoring axis.**
→ See EXPLORATION_SUMMARY.md § "4. REWARD FUNCTIONS" (function signature pattern) + § "3. EMISSIONS CALCULATION" (how to add a new pool)

**Q: I want to tweak edge decay.**
→ Set `AXON_EDGE_DECAY_RATE` and `AXON_EDGE_DECAY_FLOOR`. See QUICK_REFERENCE.md § "Configuration"

**Q: I want to test a miner implementation.**
→ Register handler in MockDendrite, call `validator.run_epoch()`. See tests/test_integration.py for pattern.

---

### Operations

**Q: What does the validator do each epoch?**
→ Read QUICK_REFERENCE.md § "Validator Epoch Loop" (8 steps)

**Q: How are weights set on-chain?**
→ `subtensor.set_weights(wallet, netuid, uids, weights, mechid=0, wait_for_inclusion=False)`. See EXPLORATION_SUMMARY.md § "2. VALIDATOR IMPLEMENTATION" § "set_weights()"

**Q: What happens to a miner that fails corpus challenge?**
→ `score_corpus()` returns 0.0 → EmissionCalculator gates weight to 1e-6 → eventual deregistration via Yuma Consensus. See QUICK_REFERENCE.md § "Emissions Pools" or EXPLORATION_SUMMARY.md § "3. EMISSIONS CALCULATION"

---

### Architecture

**Q: Why three emission pools?**
→ Different incentives: Traversal (proportional reward for high-traffic), Quality (competitive softmax), Topology (rank-based structural importance). See EXPLORATION_SUMMARY.md § "RALPLAN-DR Summary" § "Decision Drivers"

**Q: Why isn't the validator tightly coupled to Bittensor?**
→ Constructor-level dependency injection. Optional kwargs fall back to real instances if None. Unlocks full testability without chain. See EXPLORATION_SUMMARY.md § "2. VALIDATOR IMPLEMENTATION" § "Constructor & Dependencies"

**Q: How does the graph store ensure thread safety?**
→ RLock protects all mutations. No deadlock risk — lock held only during operation, released immediately. See EXPLORATION_SUMMARY.md § "1. GRAPH STORE IMPLEMENTATION" § "Thread Safety"

---

## Next Session Prep

If you continue work on this project, you'll want to:

1. Keep **QUICK_REFERENCE.md** open for lookups
2. Reference **EXPLORATION_SUMMARY.md** for deep dives
3. Run `uv run pytest` to validate changes
4. Check config via `grep -n "AXON_" /subnet/config.py` before deploying

---

**End of Exploration Index**
