# Narrative Network — Bittensor Subnet 42

## A Living Knowledge Graph with Comparative Attestation

---

## 1. Market Demand

**Who pays for output and why?**

Narrative Network produces **AI-narrated knowledge traversals** — interactive sessions where users explore a living knowledge graph, with miners competing to generate the highest-quality narrative passages at each hop. This creates a novel product at the intersection of knowledge discovery, education, and interactive storytelling.

### The Output Buyers

**End Users (Knowledge Seekers):** Users submit natural-language queries ("Tell me about consciousness emergence") and traverse an evolving graph of interconnected knowledge domains. At each hop, competing miners generate narrative passages grounded in verified corpus data, offering multiple perspectives through 5 distinct personas (Scholar, Storyteller, Journalist, Explorer, Neutral Guide). Users get curated, AI-narrated knowledge journeys — not static documents, but living narratives that improve over time as miners compete on quality.

**Application Developers:** The gateway exposes a clean REST + WebSocket API (`POST /enter`, `POST /hop`, `WS /session/{id}/live`, `GET /graph/nodes`, `POST /graph/search`) enabling third-party apps to build on the knowledge graph. Any application needing structured, quality-scored knowledge retrieval with narrative context can consume the subnet's output.

**The Bittensor Ecosystem:** Subnet 42 demonstrates a new primitive — **comparative attestation** — where multiple miners independently narrate the same traversal hop, and validators score them on 4 orthogonal axes. This creates a marketplace for knowledge quality that doesn't exist in traditional search or RAG pipelines.

### Why This Demand Is Real

- **Knowledge graphs are the missing layer for LLMs.** RAG retrieval returns chunks; Narrative Network returns *journeys* through interconnected domains with quality-scored, corpus-grounded narratives.
- **Interactive exploration > static answers.** Users choose their path through branching choice cards (2-4 per hop), creating personalized learning trajectories.
- **Verified provenance.** Every corpus chunk is Merkle-proof verified (SHA-256 binary tree). Users can trust that narratives are grounded in attested source material, not hallucinated.
- **The graph evolves.** Edges strengthen with quality traversals and decay without use (0.995x per epoch). Popular, high-quality paths grow; stale paths fade. The knowledge graph is a living organism shaped by collective intelligence.

### Product Surface

The SvelteKit 5 frontend provides two modes:
- **Explore:** 3D force-directed graph visualization (Three.js/Threlte) for browsing entities, edges, and episodes
- **Traverse:** Interactive narrative gameplay with AI-generated passages, choice cards, knowledge synthesis, and scoring breakdowns

---

## 2. Economic Viability

**Sustains itself — revenue path beyond emissions.**

### Operational Costs Are Minimal

Narrative Network is designed for capital efficiency:

| Component | Resource Profile | Cost Driver |
|-----------|-----------------|-------------|
| Validator | 512Mi–2Gi RAM, 1Gi PVC | KuzuDB (embedded, no DB service) |
| Gateway | 1–4Gi RAM, HPA 2-5 pods | SentenceTransformer embeddings |
| Domain Miner | 64–128Mi RAM | Numpy cosine similarity (no vector DB) |
| Narrative Miner | 64–128Mi RAM | OpenRouter API calls (~$0.001-0.01/hop) |
| Redis | 128–320Mi RAM | Session context only |
| IPFS | 256Mi–1Gi RAM | Domain manifest storage |

**Key cost decisions:**
- **No vector database service.** Domain miners use numpy cosine similarity on in-memory embeddings. Corpus fits in memory — no ChromaDB, Pinecone, or Weaviate overhead.
- **No GPU infrastructure.** Narrative miners call OpenRouter (OpenAI-compatible API) for LLM generation. Cost per hop is pennies, not dollars.
- **Embedded graph DB.** KuzuDB runs in-process on the validator — no managed graph database service.
- **Seed data baked into Docker images.** No runtime data fetching; reproducible deployments from day one.

### Revenue Paths Beyond Emissions

1. **API Access Fees:** The gateway API can gate premium traversal features (longer sessions, priority routing, custom personas) behind TAO micropayments.
2. **Node Proposal Bonds:** Validators stake minimum 1.0 TAO to propose new knowledge domains. Bonds are returned on successful integration, burned on rejection — creating a self-sustaining curation economy.
3. **Enterprise Knowledge Graphs:** Organizations can deploy private subnet instances with proprietary corpora, using the same scoring and evolution mechanics for internal knowledge management.
4. **Alkahest Settlement Integration:** NLA (Natural Language Agreement) escrow via Arkhai Alkahest enables programmable economic contracts around graph governance — bond escrow, conditional returns, and penalty enforcement.

### Self-Sustaining Economics

The three-pool emission model ensures miners specialize and compete across multiple dimensions simultaneously. No single strategy dominates:
- **Traversal Pool (50%):** Rewards fast, relevant responses — encourages infrastructure investment
- **Quality Pool (30%):** Softmax normalization creates exponential competition — small quality improvements yield outsized rewards
- **Topology Pool (20%):** Rank-based normalization rewards structural importance — incentivizes miners to occupy bridge positions in the graph

This multi-axis competition prevents race-to-the-bottom dynamics and sustains quality even as the miner set grows.

---

## 3. Miner Task

**Clear, measurable work output with a writable miner interface.**

### Two Distinct Miner Roles

#### Domain Miner — Corpus Retrieval + Integrity Proofs

**Task:** Maintain a knowledge corpus, serve semantically relevant chunks on demand, and prove corpus integrity via Merkle proofs.

**Interface (`KnowledgeQuery` synapse):**
```python
# Input from validator
query_text: str              # Natural language query or "__corpus_challenge__"
query_embedding: list[float] # 768-dim SentenceTransformer vector

# Output from miner
chunks: list[str]            # Top-k relevant corpus passages
domain_similarity: float     # Cosine(query_embedding, corpus_centroid)
merkle_proof: dict           # SHA-256 inclusion proof for random chunk
node_id: str                 # Miner's knowledge domain
```

**What miners actually do:**
1. Embed their corpus using SentenceTransformer (`all-mpnet-base-v2`, 768-dim)
2. On query: numpy matrix multiply (`chunk_embeddings @ query_embedding`) to find top-k chunks
3. On corpus challenge: return Merkle inclusion proof for a random chunk (SHA-256 binary tree with sibling hashes)
4. Fallback: if domain similarity < 0.35, fetch external context via Unbrowse.ai

**Measurable:** Chunk relevance (cosine similarity), response latency (< 3s target), Merkle proof validity (binary pass/fail).

#### Narrative Miner — AI-Narrated Knowledge Hops

**Task:** Generate narrative passages that bridge two knowledge domains, grounded in retrieved corpus chunks.

**Interface (`NarrativeHop` synapse):**
```python
# Input from validator
destination_node_id: str         # Target knowledge domain
player_path: list[str]           # Nodes visited so far
path_embeddings: list[list[float]]  # Embedding history
prior_narrative: str             # Previous hop's passage
retrieved_chunks: list[str]      # Corpus context from domain miners

# Output from miner
narrative_passage: str           # 100-500 word narrative (scored)
passage_embedding: list[float]   # 768-dim embedding of passage
choice_cards: list[ChoiceCard]   # 2-4 branching options for next hop
knowledge_synthesis: str         # Compressed summary
```

**What miners actually do:**
1. Select a persona (Scholar, Storyteller, Journalist, Explorer, Neutral Guide)
2. Build a structured prompt with path context, corpus chunks, and destination info
3. Call OpenRouter LLM (temperature 0.75, max 400 tokens, JSON schema enforced)
4. Return structured response: narrative + choice cards + synthesis

**Measurable:** Path coherence (cosine similarity to running path mean), directional progress (moving toward destination embedding), passage length (100-500 words optimal), and latency.

### Why This Interface Works

- **Deterministic verification:** Corpus integrity is binary (Merkle proof valid or not). No subjective judgment needed.
- **Embedding-based scoring:** All quality metrics use cosine similarity on 768-dim vectors — fast, reproducible, objective.
- **Clear spec:** Word count bounds, latency limits, required fields, and JSON schema are all enforced. Miners know exactly what to produce.
- **Low barrier to entry:** Domain miners need only a text corpus + numpy. Narrative miners need only an OpenRouter API key. No GPU required.

---

## 4. Validator Scoring

**Quality measurement method — cost-efficient, scalable evaluation loop.**

### Four-Axis Scoring System

Every epoch (60 seconds), the validator samples 10 miners and scores each on 4 orthogonal axes:

#### Axis 1: Traversal Score (Weight: 0.40)
```
chunk_relevance = cosine(chunks_embedding, query_embedding)        # 60%
groundedness = cosine(passage_embedding, domain_centroid)           # 40%
latency_penalty = min((process_time - 3.0s) * 0.10, 0.50)

score = (0.6 × chunk_relevance + 0.4 × groundedness) × (1.0 - latency_penalty)
```
**What it measures:** Are the retrieved chunks relevant? Is the passage grounded in the domain? Is the response fast?

#### Axis 2: Quality Score (Weight: 0.30)
```
path_coherence = cosine(passage_embedding, mean(all_path_embeddings))  # 40%
directional_progress = max(0, dest_sim - src_sim)                      # 30%
length_score = 1.0 if 100 ≤ words ≤ 500, else 0.2-0.6                # 30%

score = 0.4 × path_coherence + 0.3 × directional_progress + 0.3 × length_score
```
**What it measures:** Does the narrative flow coherently? Does it advance toward the destination? Is it appropriately sized?

#### Axis 3: Topology Score (Weight: 0.15)
```
bc = min(betweenness_centrality, 1.0)                                # 60%
ew = min(log(1 + edge_weight_sum) / log(1 + 50), 1.0)               # 40%

score = 0.6 × bc + 0.4 × ew
```
**What it measures:** Is this node structurally important? Does it bridge between graph regions?

#### Axis 4: Corpus Integrity (Weight: 0.15)
```
score = 1.0 if merkle_root_matches
      | 0.3 if partial_match
      | 0.0 if invalid   → GATES total weight to 1e-6 (deregistration)
```
**What it measures:** Can the miner cryptographically prove their corpus is authentic?

### Cost Efficiency

| Scoring Operation | Compute Cost | Scaling |
|-------------------|-------------|---------|
| Cosine similarity | O(768) dot product | Trivial — microseconds |
| Merkle proof verification | O(log n) hash checks | ~20 hashes for 1M chunks |
| Betweenness centrality | O(V × E) Brandes | Cached, recomputed periodically |
| Word count | O(n) string split | Trivial |
| Embedding generation | SentenceTransformer forward pass | ~50ms on CPU |

**No LLM calls by validators.** All quality assessment uses embedding similarity and cryptographic proofs — no expensive judge-LLM inference. Validators run on 512Mi–2Gi RAM with no GPU.

### Scalability

- **10 miners sampled per epoch** (configurable `CHALLENGE_SAMPLE_SIZE`): Linear scaling with miner count
- **60-second epochs** (`EPOCH_SLEEP_S`): Consistent scoring cadence regardless of network size
- **Moving average smoothing** (α=0.1): `scores = 0.1 × new + 0.9 × old` — reduces variance, prevents single-epoch manipulation
- **All scoring is local:** Validators compute scores independently using their own graph state and embeddings — no cross-validator communication needed

---

## 5. Incentive Design

**Why scoring rewards genuine quality. Why top attack vectors fail.**

### Multi-Axis Competition Prevents Single-Strategy Dominance

The three emission pools use **different normalization strategies**, preventing any single optimization from capturing all rewards:

| Pool | Share | Normalization | Effect |
|------|-------|---------------|--------|
| Traversal | 50% | **Linear** (score × count) | Rewards consistent high-volume, high-quality service |
| Quality | 30% | **Softmax** (exponential) | Small quality improvements → outsized reward gains |
| Topology | 20% | **Rank** (ordinal position) | Structural importance matters, not raw score magnitude |

**Why this works:** A miner optimizing only for traversal speed (low latency, generic chunks) will lose on quality. A miner optimizing only for narrative quality will lose on traversal volume. A miner in a dead-end graph position loses topology rewards regardless of quality. **The optimal strategy is genuine, well-rounded excellence.**

### Attack Vector Analysis

#### Attack: Corpus Fabrication
**Method:** Serve fake chunks that happen to be semantically similar to queries.
**Defense:** Merkle proof challenges select **random chunks** from the miner's declared corpus. The validator knows the expected Merkle root. Fabricated corpora produce invalid proofs → corpus score = 0.0 → emission weight floored to 1e-6 → automatic deregistration via Yuma Consensus. **Zero tolerance.**

#### Attack: Latency Gaming (Copy-Paste Fast Responses)
**Method:** Return pre-cached, generic responses instantly to win on latency.
**Defense:** Traversal scoring weights relevance at 60% and groundedness at 40%. Generic responses score low on `cosine(passage_embedding, domain_centroid)`. The latency penalty only starts at 3 seconds — there's no reward for being faster than 3s, only penalty for being slower. Fast garbage loses to slower quality.

#### Attack: Sybil Nodes (Flood Graph with Low-Quality Nodes)
**Method:** Propose many cheap nodes to capture topology rewards.
**Defense:** Each proposal requires minimum 1.0 TAO bond (burned on rejection). Stake-weighted voting requires 10% quorum + 60% approval. Integration ramp requires score ≥ 0.50 during 2-hour observation. Pruning removes nodes with score < 0.20 for 3 consecutive epochs. **Economic cost of sybil attacks exceeds potential rewards.**

#### Attack: Topology Manipulation (Create Artificial Bridge Positions)
**Method:** Create edges to position a node as a bridge.
**Defense:** Betweenness centrality uses **unweighted shortest paths** (Brandes algorithm) — creating many weak edges doesn't help. Topology pool uses **rank normalization**, not raw scores — one outlier can't capture disproportionate rewards. Edge decay (0.995x/epoch) naturally removes unused connections.

#### Attack: Quality Score Farming (Verbose, Incoherent Passages)
**Method:** Generate long, keyword-stuffed passages to maximize embedding similarity.
**Defense:** Word count scoring penalizes both under-100 (score: 0.2) and over-500 (score: 0.6) word passages. Path coherence measures similarity to the **running mean** of all prior path embeddings — random keyword stuffing diverges from coherent paths. Directional progress requires measurable movement toward the destination embedding.

#### Attack: Validator Collusion
**Method:** Validators coordinate to inflate scores for specific miners.
**Defense:** Multiple validators independently score miners and commit weights via Bittensor's **Yuma Consensus**. Outlier validators (whose weights diverge from consensus) receive reduced validator emissions. The protocol's game theory aligns validators toward honest scoring.

### Economic Flywheel

```
Quality traversals → Edge reinforcement → Popular paths emerge →
More user sessions → More scoring data → Better miner differentiation →
Higher rewards for quality → Stronger competition → Better quality
```

Conversely:
```
Low quality → Edge decay → Fewer traversals → Lower scores →
Pruning warnings → Node collapse → Bond burned → Proposer penalized
```

The system creates a **self-reinforcing quality loop** where good work begets good rewards, and poor work is automatically eliminated.

---

## 6. Technical Feasibility

**Credible mainnet path, working implementation, production infrastructure.**

### Working Implementation

The codebase contains a **complete, deployable system** — not a prototype or whitepaper:

| Layer | Status | Evidence |
|-------|--------|----------|
| Wire Protocol | Complete | `KnowledgeQuery` + `NarrativeHop` synapses with full field specs |
| Domain Miner | Complete | Corpus loading, embedding, numpy retrieval, Merkle proof generation |
| Narrative Miner | Complete | 5 personas, OpenRouter integration, JSON schema responses |
| Validator | Complete | 4-axis scoring, 3-pool emissions, moving average, weight setting |
| Graph Store | Complete | KuzuDB persistence, Brandes centrality, edge decay, traversal logging |
| Evolution | Complete | Proposal bonding, stake-weighted voting, 3-phase integration, 3-phase pruning |
| Gateway | Complete | FastAPI with REST + WebSocket, session management, safety guards |
| Frontend | Complete | SvelteKit 5, 3D graph visualization, traverse UI, Storybook components |
| Infrastructure | Complete | K8s manifests, HPA, StatefulSets, ConfigMaps, Ingress with TLS |

### Subnet API Usage

Built on **Bittensor SDK v10** (capitalized API: `bt.Wallet`, `bt.Subtensor`, `bt.AxonInfo`):
- Metagraph sync every epoch for miner discovery
- `subtensor.set_weights()` for Yuma Consensus participation
- Axon priority scoring via `metagraph.S[uid]` (stake-based)
- Validator permit checks (`metagraph.validator_permit[uid]`)

### Kubernetes Deployment — One Command

```bash
kubectl apply -k k8s/
```

Deploys the full stack: validator (StatefulSet), gateway (HPA 2-5), domain miner, narrative miner, frontend (2 replicas), Redis, IPFS, ingress with Let's Encrypt TLS.

**All 69 tunable parameters** are configurable via ConfigMap with `AXON_` prefix — zero code changes for testnet → mainnet transition:
```yaml
AXON_NETWORK: "finney"     # Switch from local → testnet → mainnet
AXON_NETUID: "42"           # Subnet 42
AXON_TRAVERSAL_WEIGHT: "0.40"
AXON_EPOCH_SLEEP_S: "60"
# ... 65 more parameters
```

### Local Development Without Bittensor

```bash
AXON_NETWORK=local uv run narrative-gateway
```

All services run in-process with no wallet, no subtensor connection, and no registration required. Developers can build, test, and iterate without touching the blockchain.

### Docker Multi-Stage Builds

- **Python image:** Base layer (gcc, deps) → 4 specialized targets (gateway, validator, domain-miner, narrative-miner)
- **Frontend image:** node:22-alpine build → minimal runtime
- **Seed topology and corpora baked into images** — no external data fetching at startup

### Test Infrastructure

- **Python:** pytest with asyncio auto mode, ruff linting (line-length 100, Python 3.12 target)
- **TypeScript:** Vitest (browser + server projects), Playwright E2E, ESLint + Prettier
- **Storybook:** Component isolation testing on port 6006

### Production Domain

Ingress configured for **futograph.online** with Let's Encrypt TLS — live deployment target with production-grade SSL.

---

## Sovereignty Test

**Subnet survives if any single cloud, company, API, or person disappears.**

### No Single Points of Failure

| Dependency | Failure Mode | Survival Mechanism |
|------------|-------------|-------------------|
| **Cloud provider** | AWS/GCP/Hetzner goes down | K8s manifests are portable; redeploy on any provider. No cloud-specific services used. |
| **OpenRouter API** | LLM provider unavailable | Narrative miners can swap to any OpenAI-compatible endpoint via `OPENROUTER_BASE_URL` env var. Unbrowse fallback for context. |
| **IPFS node** | Storage unavailable | Domain manifests cached locally; miners hold their own corpus data in-memory. IPFS is supplementary, not critical path. |
| **Redis** | Session store down | `SessionStore` has in-memory fallback (`InMemorySessionStore`). Sessions degrade gracefully. |
| **PostgreSQL** | Frontend DB down | Only stores minimal data (user table). Frontend can operate in read-only graph mode. |
| **Any single validator** | Validator goes offline | Multiple validators score independently via Yuma Consensus. Network continues with remaining validators. |
| **Any single miner** | Miner deregisters | Other miners serve the same knowledge domains. Graph routing adapts to available miners. |
| **Original team** | Developers leave | Open protocol on Bittensor. Any team can run validators, miners, and gateways. No API keys, subscriptions, or vendor lock-in. |

### Decentralization Architecture

- **Consensus:** Bittensor's Yuma Consensus (Substrate chain) — not a custom BFT implementation
- **Data ownership:** Miners own and prove their corpus via Merkle trees. Validators observe and score but don't store miner data.
- **Governance:** On-chain, stake-weighted proposal voting — no admin keys, no multisigs, no single decision-maker
- **Settlement:** Arkhai Alkahest NLA escrow — bond returns/burns enforced by protocol, not operator
- **Graph state:** Each validator maintains an independent KuzuDB instance. Consensus emerges from collective weight-setting, not a shared database.

### No Rent Extraction

- No API keys required for subnet access (Bittensor wallet + stake)
- No subscription fees
- No vendor lock-in (open protocol, forkable)
- No ads or tracking
- Miners earn by providing quality; validators earn by scoring fairly

---

## Summary

Narrative Network is a **production-ready, sovereign knowledge graph** on Bittensor Subnet 42 that:

1. **Creates real demand** — interactive AI-narrated knowledge traversals that improve over time
2. **Sustains itself** — minimal operational costs (no GPU, no vector DB), multiple revenue paths, self-reinforcing quality economics
3. **Defines clear miner tasks** — two roles with precise interfaces, deterministic scoring, and low barriers to entry
4. **Scores efficiently** — 4-axis embedding + cryptographic evaluation with zero LLM cost for validators
5. **Aligns incentives** — 3-pool emissions with different normalizations, Merkle-gated corpus integrity, economic penalties for gaming
6. **Ships working code** — complete implementation from wire protocol to 3D frontend, deployable with `kubectl apply -k k8s/`
7. **Survives anything** — no single cloud, company, API, or person is a dependency
