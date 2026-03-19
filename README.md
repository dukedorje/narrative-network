# Bittensor Knowledge Network (BKN)

**A living knowledge graph on Bittensor where traversal is the thinking.**

[futograph.online](https://futograph.online)

---

Bittensor Knowledge Network (BKN) is a Bittensor subnet that maintains a living knowledge graph — one that grows, forgets, and evolves through the paths taken through it. Miners register as knowledge domain nodes, serve grounded retrieval and narrative authoring, and compete for TAO emission by producing high-quality traversal experiences. Validators score responses comparatively, maintain graph topology, and commit consensus weights to chain.

The network doesn't store knowledge. It *simulates* knowledge through traversal. Every path a user takes reinforces the edges walked and lets untraveled paths decay — producing, over time, the network's best theory of how domains of understanding relate to each other.

## How It Works

```
User (soul token) → Gateway (embed, route) → Domain Miners (chunk retrieval)
  → Narrative Miners (passage + choices) → Validator (score, set weights)
  → Graph Store (reinforce edges, decay unused paths)
```

1. **Enter.** You submit a query — your "soul token." The gateway embeds it and cosine-compares against every node's domain centroid. The best-matching node becomes your entry point.

2. **Traverse.** At each node, narrative miners compete to author a passage that synthesizes retrieved knowledge chunks with your traversal history. You receive the winning passage and a set of choice cards branching to adjacent domains.

3. **Evolve.** Every hop is logged as edge reinforcement. Paths taken often become canonical routes; paths ignored decay. New nodes proposed by miners can fracture existing topology and spawn new narrative branches.

4. **Score.** Validators score miners on four axes — traversal relevance, narrative quality, topological importance, and corpus integrity — without ground truth. Comparative attestation ranks competing responses against attractor basins, not absolute answers.

## Core Ideas

**Hallucination as controlled exploration.** LLM hallucination isn't minimized — it's the simulation's step size through possibility-space. Bounded by attractor basins (centroid embeddings) and scored by validators, hallucination becomes directed speculation. The scoring criteria aren't quality control — they are *physics*: distance from centroid is travel through phase-space, coherence scoring is conservation of energy, validators are laws of motion.

**Comparative attestation without ground truth.** Multiple miners produce competing responses at each hop. Validators rank them relative to domain centroids and narrative continuity — not against some canonical answer. The accumulated attestations, not the narratives themselves, are the knowledge the network produces.

**Three-pool emission model.** Miner rewards come from three pools with different competitive dynamics:
- **Traversal (50%)** — rewards high-traffic, high-relevance nodes (volume x quality)
- **Quality (30%)** — softmax sharpens competition at the top of the distribution
- **Topology (20%)** — rewards structurally important bridge nodes by betweenness centrality, independent of traffic

This gives new miners a viable strategy: extend into underserved knowledge regions rather than competing head-to-head on popular domains.

**Living topology.** Edges decay multiplicatively each epoch (collective forgetting) and strengthen through quality traversals (collective learning). Nodes that drift from their declared centroid are detected and re-incubated. Pruned nodes trigger collapse narratives — the graph doesn't just change, it tells the story of its own evolution.

## Scoring

Validators score miners on four axes (`subnet/reward.py`):

| Axis | Weight | What it measures |
|------|--------|------------------|
| Traversal relevance | 40% | Did the hop actually connect the concepts? (cosine similarity + latency) |
| Narrative quality | 30% | Is the generated text coherent and grounded? |
| Topology importance | 15% | Is this node structurally central to the graph? (betweenness centrality) |
| Corpus integrity | 15% | Are Merkle proofs valid and stable? |

Corpus integrity is a **binary gate** — a zero corpus score collapses the miner's combined weight to near-zero regardless of performance on the other axes. This is the primary anti-fraud mechanism.

## Architecture

| Component | Role | Key Module |
|-----------|------|------------|
| Gateway | Internet-facing API, session lifecycle, embedding | `orchestrator/gateway.py` |
| Miner | Unified corpus retrieval + Merkle proofs + LLM narrative authoring via OpenRouter | `domain/unified_miner.py` |
| Validator | Four-axis scoring, weight commit via Yuma Consensus | `subnet/validator.py` |
| Graph Store | Edge weights, centrality, decay, traversal logs (KuzuDB embedded) | `subnet/graph_store.py` |
| Emission Calculator | Three-pool weight vector generation | `subnet/emissions.py` |
| Evolution System | Proposals, voting, pruning, integration | `evolution/` |
| Web Frontend | SvelteKit 5 traversal interface | `src/` |

### Synapse Protocol

Two synapse types flow over Bittensor's transport:

- **KnowledgeQuery** — Gateway → Domain Miners. Retrieves top-k corpus chunks with Merkle proofs. Also used for corpus integrity challenges.
- **NarrativeHop** — Gateway → Narrative Miners. The core game loop. Carries destination node, player path, prior narrative, and retrieved chunks. Returns a passage, choice cards, and knowledge synthesis.

### Node Lifecycle

```
Proposed → Voting → Incubating → FORESHADOW → BRIDGE → LIVE → (WARNING → DECAYING → COLLAPSED)
                                                          ↑
                                                      Drift detected → re-incubation
```

New nodes enter through stake-weighted voting, pass an incubation period with shadow scoring, then integrate in three phases: **Foreshadow** (adjacent miners weave hints into their narratives), **Bridge** (edge weights ramp linearly from zero), and **Live** (full competition). Proposers lock a TAO bond that is returned on successful integration or burned on rejection/collapse.

Pruning is also gradual: **Warning** → **Decaying** (aggressive edge decay) → **Collapsed** (removal). Sessions never reach dead ends — pruning triggers collapse narratives and rerouting, not errors.

### External Integrations

**[Unbrowse](https://unbrowse.ai)** — Live web context fallback. When corpus coverage is insufficient (`domain_similarity < 0.35`), domain miners fetch web snippets via Unbrowse to supplement responses. Narrative miners also inject web context as additional grounding for the LLM prompt. Unbrowse is also used to validate real-world coverage before accepting new node proposals. All calls are non-blocking — errors silently return empty results, so Unbrowse availability never impacts traversal latency.

**[Arkhai / Alkahest](https://www.arkhai.io)** — On-chain settlement for governance bonds via the Alkahest protocol (EAS-based escrow). When a miner proposes a new node, they lock a TAO bond into an Alkahest escrow (`evolution/nla_settlement.py`). The bond is returned if the node reaches Live status, or burned to treasury if rejected by vote or collapsed during pruning. All NLA calls are non-blocking.

## Seed Topology

The initial graph spans 16 nodes across 13 knowledge domains:

Quantum Mechanics (foundations, phenomena, interpretations, bridge) · Relativity · Thermodynamics · Chemical Bonding · Reaction Kinetics · Stellar Dynamics · Evolution · Topology · Recursion · Information Theory · Consciousness · Epistemology · Emergence

Each node is backed by a real text corpus embedded via `all-mpnet-base-v2` (768-dim). Edges encode conceptual proximity — quantum mechanics connects to relativity, thermodynamics bridges to chemical bonding, information theory links to consciousness.

## Quick Start

### Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js 22+
- Redis (session persistence)
- PostgreSQL (frontend database)

### Local Dev Gateway (no Bittensor required)

```bash
# Install Python dependencies
uv sync --extra dev

# Source environment variables
source .env

# Start the dev gateway on :8080
AXON_NETWORK=local uv run narrative-gateway
```

The dev gateway runs all miners in-process — loads the seed topology, does chunk retrieval via numpy, and calls OpenRouter for narrative generation. No Bittensor wallet or subtensor needed.

```bash
# Test it
curl -X POST http://localhost:8080/enter \
  -H "Content-Type: application/json" \
  -d '{"query_text": "What is quantum entanglement?"}'

# Then hop
curl -X POST http://localhost:8080/hop \
  -H "Content-Type: application/json" \
  -d '{"session_id": "<id>", "destination_node_id": "quantum-phenomena"}'
```

### Web Frontend

```bash
npm install
npm run dev          # Dev server on :5173
```

### Run Tests

```bash
uv run pytest                    # Python (223 tests)
npm run test:unit -- --run       # TypeScript
```

### Kubernetes

```bash
kubectl apply -k k8s-local/     # Local stack
kubectl apply -k k8s/           # Production
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/enter` | Start a traversal session with a soul token query |
| `POST` | `/hop` | Advance to a destination node, receive narrative + choices |
| `GET` | `/session/{id}` | Get session state and path |
| `WS` | `/session/{id}/live` | Real-time narrative streaming |
| `GET` | `/graph/nodes` | List all live nodes with adjacency |
| `GET` | `/graph/stats` | Graph statistics (node/edge counts) |
| `GET` | `/healthz` | Health check |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | LLM narrative generation (required) |
| `DATABASE_URL` | PostgreSQL for frontend |
| `REDIS_URL` | Session persistence (falls back to in-memory) |
| `AXON_NETWORK` | Set to `local` for dev mode |
| `BT_WALLET_MNEMONIC` | Bittensor wallet (production only) |

All subnet constants in `subnet/config.py` can be overridden with the `AXON_` prefix (e.g., `AXON_TRAVERSAL_WEIGHT=0.5`).

## Tech Stack

**Subnet:** Python 3.12, Bittensor SDK v10, FastAPI, sentence-transformers, numpy, KuzuDB, Redis, OpenRouter

**Frontend:** SvelteKit 5, Svelte 5, Tailwind CSS 4, Drizzle ORM, Paraglide i18n

**Infrastructure:** Kubernetes (Kustomize), Docker multi-stage builds

## Documentation

Detailed architecture docs live in `docs/`:

- [Vision](docs/narrative/vision.md) — the network that thinks by being traversed
- [System Overview](docs/architecture/system-overview.md) — component map and data flow
- [Synapse Protocol](docs/architecture/synapse-protocol.md) — wire format and sequence diagrams
- [Scoring & Validation](docs/architecture/scoring-and-validation.md) — four-axis comparative attestation
- [Emission Model](docs/architecture/emission-model.md) — three pools, formulas, economic properties
- [Node Lifecycle](docs/architecture/node-lifecycle.md) — proposal to pruning state machine
- [Graph Store](docs/architecture/graph-store.md) — edge dynamics, centrality, decay
- [Session Management](docs/architecture/session-management.md) — continuity invariants
- [Incentive Alignment](docs/economics/incentive-alignment.md) — game theory and attack vectors
- [Product Requirements](docs/prd.md) — full PRD with user stories

## License

MIT
