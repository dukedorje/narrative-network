# Narrative Network — Product Requirements Document

**Subnet:** Bittensor (subnet ID TBD)
**Status:** Pre-alpha / Architecture
**Last updated:** 2026-03-15

---

## 1. Product Overview

The Narrative Network is a Bittensor subnet that creates and maintains a **living knowledge graph** — one that grows, forgets, and evolves through the paths taken through it. Miners register as knowledge domain nodes, serve chunk retrieval and narrative authoring, and compete for TAO emission by producing high-quality traversal experiences. Validators score responses comparatively, maintain graph topology, and commit consensus weights to chain.

The network is designed to be **general-purpose** — while initially bootstrapped from an existing knowledge graph system (bonfires.ai), the architecture supports any knowledge graph representation.

### 1.1 Core Value Proposition

- **For miners:** Earn TAO by serving knowledge domains with quality retrieval and compelling narrative authoring. Three revenue channels: traversal credits, quality bonuses, and topology rewards.
- **For validators:** Earn from the quality pool by honestly scoring miner responses. Maintain the living graph topology as infrastructure.
- **For users:** Traverse a living knowledge graph where every path creates new understanding. Receive grounded, coherent narrative passages synthesizing domain knowledge with traversal context.
- **For the network:** Produce a continuously-validated theory of knowledge topology — the combined phase-space of all traversals, weighted by accumulated attestations.

### 1.2 Key Innovation

LLM hallucination is not minimized but **harnessed** — it is the simulation's step size through possibility-space. Bounded by attractor basins (centroid embeddings) and scored by validators, hallucination becomes controlled exploration. The evaluation criteria are not quality control — they are **physics**: distance from centroid is travel through phase-space, coherence scoring is conservation of energy, validators are laws of motion.

---

## 2. User Stories

### 2.1 Miner — Domain Node Operator

**As a domain miner**, I want to register a knowledge domain (corpus + centroid embedding + persona) so that I can earn TAO by serving retrieval queries grounded in my domain.

Acceptance criteria:
- Submit domain manifest to IPFS with corpus Merkle root, centroid embedding, and narrative persona
- Stake TAO bond via proposal system
- Pass incubation period (shadow scoring with no live traffic)
- Serve KnowledgeQuery synapses with top-k chunks + Merkle root within 3s timeout
- Survive corpus integrity challenges (Merkle root stability)

**As a narrative miner**, I want to author compelling traversal passages so that my responses win sessions and earn traversal credits.

Acceptance criteria:
- Receive NarrativeHop synapse with destination node, player path, prior narrative, and retrieved chunks
- Return narrative passage (200-400 tokens, second-person present tense) + 2-4 choice cards + knowledge synthesis
- Highest-scoring response wins the session
- Weave foreshadowing when integration_notice is present (new node bridging)

### 2.2 Validator — Scoring and Consensus

**As a validator**, I want to score miner responses fairly and commit weights to chain so that the network rewards quality and maintains honest topology.

Acceptance criteria:
- Run epoch scoring loop: sample challenge pairs, issue KnowledgeQuery + NarrativeHop challenges
- Score on four axes: traversal (cosine similarity + latency), quality (word-count heuristic, future: embedding coherence), topology (betweenness centrality + edge weight), corpus integrity (Merkle stability)
- Call `subtensor.set_weights()` independently (SDK v10 API, `mechid=0`); Yuma Consensus aggregates across validators
- Commit-reveal v4 (Drand time-lock encryption) prevents weight copying when `CommitRevealWeightsEnabled = True`
- Apply edge decay after each epoch
- Detect semantic drift (centroid divergence over time)

### 2.3 User — Graph Traverser

**As a user**, I want to enter the knowledge graph with a query and traverse it by choosing narrative paths, receiving grounded and coherent passages at each step.

Acceptance criteria:
- Submit soul token (text query) via REST or WebSocket
- Receive entry node assignment based on cosine similarity to domain centroids
- At each node: see narrative passage + choice cards to adjacent nodes
- Path state maintained across hops (session tracks visited nodes, accumulated narrative)
- Never reach a dead end due to graph mutation (continuity invariant)
- Session terminates gracefully at max_hops or when no next nodes available

### 2.4 Proposer — New Node Introduction

**As a miner**, I want to propose new knowledge domains to the graph so that the network's coverage expands.

Acceptance criteria:
- Submit NodeProposal with bond, domain manifest, proposed adjacency
- Proposal enters stake-weighted voting (fixed block window)
- If accepted: incubation → integration (24h bridge window with linear edge weight ramp) → live
- If rejected: bond returned (minus any slash for fraud)
- Integration includes foreshadowing in adjacent nodes' narratives

---

## 3. System Architecture

### 3.1 Component Map

| Component | Role | Resources | Key Module |
|-----------|------|-----------|------------|
| Gateway VM | Internet-facing API, session ownership | FastAPI + sentence-transformers | `orchestrator/gateway.py` |
| Domain Miner | Corpus retrieval, Merkle proofs | ~2 vCPU, 4GB RAM | `domain/miner.py`, `domain/corpus.py` |
| Narrative Miner | Passage authoring, choice cards | ~2 vCPU, 4GB RAM (OpenRouter, no GPU) | `domain/narrative/miner.py` |
| Validator | Scoring, weight commit, graph maintenance | ~8 vCPU, 32GB | `subnet/validator.py` |
| Graph Store | Edge weights, centrality, traversal logs | KuzuDB + in-memory | `subnet/graph_store.py` |
| Subtensor | UID registry, stake, emission | Bittensor chain | finney / local testnet |

### 3.2 Synapse Protocol

Three message types (see `subnet/protocol.py`):

1. **KnowledgeQuery** — Retrieval synapse. Orchestrator broadcasts to all miners on entry; validators use for scoring and corpus challenges.
2. **NarrativeHop** — Traversal synapse. Core game loop. Destination node's miners compete to author the best passage.
3. **WeightCommit** — Internal validator dataclass for accumulating scores before set_weights. Not transmitted over the network.

### 3.3 Data Flow

```
User (soul token) → Gateway (embed, route) → KnowledgeQuery (broadcast)
  → Domain Miners (top-k chunks) → Gateway (select entry node)
  → NarrativeHop (to destination miners) → Narrative Miners (passage + choices)
  → Gateway (select winner, stream to user)

Validator (per epoch):
  → Sample challenges → Score (traversal + quality + topology + corpus)
  → subtensor.set_weights() (each validator independently; Yuma Consensus aggregates)
  → graph_store.decay_edges
```

---

## 4. Emission Model

### 4.1 Pool Distribution

Three emission pools shape the miner weight vector submitted to Yuma Consensus. Each uses a different normalization strategy (see `subnet/emissions.py`):

| Pool | Share | Normalization | What it rewards |
|------|-------|---------------|-----------------|
| TraversalPool | 50% | Linear | High-traffic, high-relevance nodes (`traversal_score * traversal_count`) |
| QualityPool | 30% | Softmax | Competitive narrative quality scores |
| TopologyPool | 20% | Rank-based | Structurally important bridge nodes |

**Corpus integrity** is not a pool — it is a binary gate. `corpus_score == 0.0` collapses the miner's combined weight to `1e-6` regardless of pool performance.

**There is no separate reserve pool.** The protocol's 18% owner share (fixed by dTAO) funds proposal bond returns and operations.

### 4.2 Key Economic Properties

- **Quality compounding:** Higher scores → more session wins → more TAO → better infrastructure → higher scores. Softmax in QualityPool sharpens this effect at the top of the distribution.
- **Structural rewards:** Bridge nodes earn TopologyPool rewards from day one, independent of traffic volume. The answer to "how do new miners compete?"
- **Corpus enforcement:** Corpus fraud collapses emission to near-zero, overriding all pool scores — the primary anti-fraud mechanism.
- **No separate validator pool:** Validators earn from the protocol's 41% validator+staker share via Yuma Consensus bond mechanism, not from a custom emission pool.

---

## 5. Graph Evolution Protocol

### 5.1 Node Lifecycle

```
Proposed → Voting → Incubating → Integrating → Live → (Pruned)
                                                  ↑
                                              Drift detected → re-incubation
```

### 5.2 Integration Bridge Window

- ~24 hours (7,200 blocks)
- Edge weights ramp linearly from 0.0 to proposed values
- Visibility threshold: 0.05 (choice cards appear only after this)
- Adjacent miners receive integration notices for narrative foreshadowing

### 5.3 Pruning and Continuity

- Rolling attestation window for quality/traffic monitoring
- Warning → accelerated decay → grace window → gradual edge zeroing
- **Continuity invariant:** No active session ever reaches a dead end from graph mutation
- Collapse events: generated narrative explaining domain dissolution
- Bridge narratives: fault-line passages for rerouted sessions

---

## 6. Settlement Layer — Arkhai/Alkahest Integration

The Alkahest protocol (escrow + arbiter + fulfillment on EAS) provides a natural settlement layer for the subnet's economic flows:

### 6.1 Traversal Credits as Escrow Obligations

Each completed hop creates an Alkahest escrow obligation. The validator acts as the arbiter, releasing TAO to the winning miner when quality thresholds are confirmed. This creates an on-chain attestation trail (via EAS) for every traversal credit.

### 6.2 Domain Manifests as Natural Language Agreements

Miners' domain manifests — declarations of what they know and how they speak — can be expressed as Alkahest obligations with algorithmic arbiters that programmatically verify corpus integrity (Merkle root checks) and centroid embedding validity.

### 6.3 Proposal Bonds as Alkahest Escrows

Proposal bonds locked via Alkahest escrow contracts. Multi-validator arbiter committees adjudicate slash/return decisions. Bond lifecycle (lock → vote → return/slash) managed via Alkahest SDK.

### 6.4 Benefits

- Composable settlement primitives (not a monolithic payment system)
- Auditable on-chain trail via EAS attestations
- SDK support (TypeScript, Rust, Python) for programmatic bond/escrow management
- Natural language agreement readability for manifest terms

---

## 7. External Dependencies

| Dependency | Purpose | Status |
|------------|---------|--------|
| Bittensor SDK | Synapse transport, metagraph, subtensor | Required |
| KuzuDB | Graph persistence | Optional (in-memory fallback) |
| sentence-transformers | Embedding (768-dim) | Required for gateway + validators |
| OpenRouter API | Narrative generation (OpenAI-compatible) | Required for narrative miners (no GPU needed) |
| IPFS (Kubo) | Manifest + centroid storage | Required for registration |
| Redis | Session cache (multi-instance) | Implemented (in-memory fallback available) |
| Kubernetes | Container orchestration | Manifests in `k8s/` (Kustomize) |
| Prometheus + Grafana | Observability | Recommended |
| bonfires.ai | Initial knowledge graph bootstrap | Integration planned |
| Arkhai/Alkahest | Settlement layer | Integration planned |

---

## 8. Milestones

### Phase 1 — Local Testnet (MVP)

- [ ] Subnet registration on local subtensor
- [ ] 3+ domain miner nodes with real corpora
- [ ] 1+ narrative miner per domain node
- [ ] 1+ validator running full scoring loop
- [x] Gateway serving /enter and /hop over REST (`orchestrator/gateway.py`)
- [x] Graph store with edge weight updates and decay (`subnet/graph_store.py`)
- [x] Emission model implementation (3 pools + corpus gate) (`subnet/emissions.py`)
- [x] Orchestrator session management (`orchestrator/`)
- [ ] Basic proposal flow (propose → vote → integrate)
- [ ] End-to-end traversal demo: soul token → entry → 5 hops → terminal
- [ ] Local testnet integration testing (all components wired together)

### Phase 2 — Finney Testnet

- [ ] Deploy to Bittensor finney testnet
- [ ] Miner registration via IPFS manifests
- [ ] Corpus integrity challenges (Merkle verification)
- [ ] WebSocket streaming for real-time hop delivery
- [ ] Session persistence in Redis
- [ ] Semantic drift detection
- [ ] Integration bridge window with foreshadowing
- [ ] Emission model wired to scoring loop and set_weights() (3 pools + corpus gate)

### Phase 3 — Mainnet + bonfires.ai Integration

- [ ] Mainnet subnet registration
- [ ] bonfires.ai knowledge graph bootstrap
- [ ] Alkahest settlement layer integration
- [ ] Player dashboard (traversal ledger, epoch settlement)
- [ ] Multi-epoch folio tracking
- [ ] NPC autonomous traversal probes
- [ ] Live graph visualization (D3 force-simulation)
- [ ] Grafana observability dashboards

### Phase 4 — Game Engine Layer

- [ ] Soul token personas with embedding evolution
- [ ] Collapse events and bridge narratives
- [ ] TAO micropayments per hop
- [ ] Graph mutation as game events (foreshadowing, dissolution)
- [ ] Multi-entity phase-space visualization
- [ ] Emergent lore system

---

## 9. Open Questions

1. **Knowledge graph bootstrap:** What is the initial node set? How many domains for MVP? What corpora seed them?
2. **Narrative miner model:** Which LLM base? Fine-tuned per domain or general with persona prompting? — **Resolved: OpenRouter API with configurable model (default mistral-7b-instruct). Persona prompting, not fine-tuning.**
3. **Embedding model:** sentence-transformers default is 768-dim. Confirm this is sufficient for domain discrimination. — **Confirmed: sentence-transformers/all-mpnet-base-v2, 768-dim.**
4. **Validator hardware:** 8 vCPU / 32GB baseline. Is GPU needed for re-embedding at scale? — **No GPU needed. Validators re-embed with CPU-based sentence-transformers.**
5. **Epoch length:** How many blocks? Trade-off between scoring freshness and computational cost. — **360 blocks (~72 minutes at 12s/block) configured in SubnetConfig.**
6. **Quality scoring evolution:** When does word-count heuristic get replaced with embedding-based coherence? What's the evaluation metric?
7. **Alkahest integration depth:** Full escrow for every traversal credit, or batch settlement per epoch?
8. **bonfires.ai integration:** API contract? Data format? Sync frequency?
9. **Subnet number:** "42" is a target. What's the actual registration process and timeline?
10. **Multi-miner competition:** How many miners can register for the same node_id? Is there a cap?

---

## 10. Document Index

| Document | Path | Description |
|----------|------|-------------|
| Foundational Vision | `docs/narrative/vision.md` | The network that thinks by being traversed |
| Initial Vision | `docs/narrative/initial-vision.md` | Comparative attestation framing |
| System Overview | `docs/architecture/system-overview.md` | VM topology, component map |
| Synapse Protocol | `docs/architecture/synapse-protocol.md` | Wire format, three synapses, sequence diagrams |
| Scoring and Validation | `docs/architecture/scoring-and-validation.md` | Four sub-scores, weight commit, epoch loop |
| Graph Store | `docs/architecture/graph-store.md` | KuzuDB, decay, centrality, traversal logging |
| Node Lifecycle | `docs/architecture/node-lifecycle.md` | Proposed to Live to Pruned state machine |
| Session Management | `docs/architecture/session-management.md` | Gateway, orchestrator, WebSocket streaming |
| Emission Model | `docs/architecture/emission-model.md` | Three pools, formulas, economic properties |
| Incentive Alignment | `docs/economics/incentive-alignment.md` | Game theory, attack vectors, compounding |
| Arkhai/Alkahest Protocol | `docs/protocols/arkhai-alkahest.md` | Settlement layer integration |
| Goals | `docs/goals.md` | Current status and milestone tracking |
| Game Engine (Future) | `docs/future/game-engine.md` | Simulation reframe, entities, emergent lore |
| Player Dashboard (Future) | `docs/future/player-dashboard.md` | Traversal ledger, epoch settlement, folio |
