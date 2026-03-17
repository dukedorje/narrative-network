# Narrative Network — Glossary

Complete terminology reference for the Narrative Network Bittensor subnet.

---

## Core Concepts

- **Knowledge Graph** — Living, evolving network of interconnected knowledge domains. Nodes are miner-owned domains; edges are weighted traversal paths. (`subnet/graph_store.py`, `README.md`)

- **Traversal / Session** — A player's path through the knowledge graph via sequential hops, tracked by `OrchestratorSession` with a unique session ID. (`orchestrator/session.py`, `subnet/protocol.py`)

- **Node** — A knowledge domain in the graph, owned by a miner. States: Live, Incubating, Pruned. Contains node_id, centroid_embedding, description, persona. (`subnet/graph_store.py`, `evolution/proposal.py`)

- **Edge** — Weighted connection between two nodes representing conceptual proximity. Reinforces on quality traversals; decays multiplicatively each epoch. (`subnet/graph_store.py`)

- **Hop** — A single step in traversal: the player selects a destination from presented choice cards. Miners compete to narrate each hop. (`subnet/protocol.py`)

- **Choice Card** — A destination option presented to the player at each hop. Contains node_id, teaser text, and relevance cues. (`subnet/protocol.py`)

- **Comparative Attestation** — Core design principle: validators rank competing miner responses relative to each other, not against ground truth. Accumulated attestations *are* the knowledge produced. (`README.md`)

- **Living Topology** — Edges reinforce and decay; nodes integrate and prune. The graph tells the story of its own evolution. (`README.md`)

- **Soul Token** — The player's initial query text that seeds entry-point resolution. (`README.md`)

- **Attractor Basin** — Region in embedding space around a node's centroid — defines its semantic "gravity well." (`README.md`)

- **Hallucination as Controlled Exploration** — Reframing of LLM hallucination as intentional speculation bounded by domain centroids. (`README.md`)

---

## Bittensor Protocol

- **Synapse** — Wire protocol message transmitted over Bittensor axon/dendrite transport. Two types: `KnowledgeQuery` and `NarrativeHop`. (`subnet/protocol.py`)

- **KnowledgeQuery** — Synapse from orchestrator/validator → miners. Retrieves top-k corpus chunks with Merkle proofs. Used for entry-point resolution, chunk retrieval during hops, and corpus integrity challenges. (`subnet/protocol.py`, `domain/unified_miner.py`)

- **NarrativeHop** — Core game-loop synapse fired each time a player selects a choice card. Request includes destination, player path, prior narrative, retrieved chunks. Response includes narrative passage, choice cards, knowledge synthesis. (`subnet/protocol.py`, `domain/unified_miner.py`)

- **Dendrite** — Outbound RPC client (orchestrator/validator calls miners). (`orchestrator/session.py`)

- **Axon** — Inbound server (miners listen for synapse requests). (`domain/unified_miner.py`)

- **Metagraph** — Bittensor's view of subnet registrations: UIDs, stake, axon info. Polled by `MetagraphWatcher` to detect registrations/deregistrations. (`subnet/metagraph_watcher.py`)

- **UID (User ID)** — Miner's numeric identifier on the metagraph (0–255 typical). Used to look up stake, axon info, and assign weights. (`subnet/validator.py`, `orchestrator/router.py`)

- **Yuma Consensus** — Bittensor mechanism for aggregating validator weights into miner emissions. Called via `subtensor.set_weights()`. (`subnet/validator.py`)

- **Hotkey** — SS58 address used by miners/validators for signing requests. (`evolution/proposal.py`)

- **Coldkey** — Wallet key that holds TAO stake (not directly referenced in code). (`evolution/proposal.py`)

- **WeightCommit** — Dataclass for committed weight values. (`subnet/protocol.py`)

- **NETUID** — Subnet ID on Bittensor mainnet. Narrative Network = 42. (`subnet/__init__.py`)

- **SPEC_VERSION** — Protocol version string; must match between synapse sender/receiver. (`subnet/__init__.py`)

- **Challenge (Corpus Integrity Challenge)** — Validator sends `query_text == "__corpus_challenge__"` to audit a miner's corpus. Miner returns chunk hashes; validator checks against committed Merkle root. (`subnet/protocol.py`)

---

## Scoring & Reward System

### Four Scoring Axes (weights sum to 1.0)

- **Traversal Relevance** (0.40) — Chunk relevance + passage groundedness + latency penalty. (`subnet/reward.py`)

- **Narrative Quality** (0.30) — Path coherence + directional progress + passage length. (`subnet/reward.py`)

- **Topology Importance** (0.15) — Betweenness centrality + edge weight sum. (`subnet/reward.py`)

- **Corpus Integrity** (0.15) — Merkle proof validation. Binary gate: zero collapses all weight. (`subnet/reward.py`)

### Scoring Sub-Components

- **Chunk Relevance** — Cosine similarity between retrieved chunk embedding and query embedding. (`subnet/reward.py`)

- **Groundedness** — Cosine similarity between passage embedding and domain centroid. Ensures narrative stays rooted in the miner's declared domain. (`subnet/reward.py`)

- **Path Coherence** — Cosine similarity between passage embedding and running mean of prior path embeddings. Rewards thematic continuity. (`subnet/reward.py`)

- **Directional Progress** — Difference in cosine similarity to destination vs. source node. Rewards passages that move toward the intended target. (`subnet/reward.py`)

- **Betweenness Centrality** — How often a node appears on shortest paths between other nodes. Computed via Brandes algorithm. Rewards structurally important "bridge" nodes. (`subnet/graph_store.py`)

- **Edge Decay** — Multiplicative decay applied to all edge weights each epoch. Implements "collective forgetting" of untraveled paths. Default rate: 0.995, floor: 0.01. (`subnet/config.py`, `subnet/graph_store.py`)

- **Reinforcement** — Edge weight increase triggered by a quality traversal. (`subnet/graph_store.py`)

- **Latency Soft Limit** — 3.0s threshold before latency penalty kicks in. Penalty: `min(excess_s × LATENCY_PENALTY_PER_S, LATENCY_MAX_PENALTY)`. (`subnet/config.py`)

- **Moving Average** — Exponential MA (alpha=0.1) smoothing validator scores across epochs. (`subnet/config.py`)

- **Traversal Count / Traversal Log** — Per-edge counter of traversals. Recorded in `TraversalLog` dataclass with session_id, passage_embedding, scores. (`subnet/graph_store.py`)

---

## Emission Model

### Three Emission Pools (sum to 100%)

- **TraversalPool** (50%) — Linear normalization over `traversal_score × traversal_count`. Proportional rewards. (`subnet/emissions.py`)

- **QualityPool** (30%) — Softmax normalization over quality scores. Competitive, winner-takes-more. (`subnet/emissions.py`)

- **TopologyPool** (20%) — Rank-based normalization over topology scores. Ordinal ranking. (`subnet/emissions.py`)

### Emission Components

- **EmissionCalculator** — Combines pool weights into final weight vector submitted to `set_weights()`. (`subnet/emissions.py`)

- **MinerScoreSnapshot** — Per-miner score record for one epoch. Fields: uid, traversal_score, quality_score, topology_score, corpus_score, traversal_count. (`subnet/emissions.py`)

- **Corpus Integrity Gate** — If `corpus_score == 0.0`, miner's combined weight → 1e-6 (near-zero emission). (`subnet/emissions.py`)

- **Normalization Strategies** — Linear (proportional), Softmax (competitive), Rank (ordinal). (`subnet/emissions.py`)

- **Dynamic TAO (dTAO)** — Bittensor protocol feature controlling emission splits. Owner: 18%, Miners: 41%, Validators+Stakers: 41%. (`docs/architecture/emission-model.md`)

---

## Graph Evolution & Node Lifecycle

### Lifecycle States

```
DRAFT → SUBMITTED → VOTING → ACCEPTED → INTEGRATING → LIVE → BOND_RETURNED
                           → REJECTED
                                         LIVE → WARNING → DECAYING → COLLAPSED
```

### Proposal & Voting

- **NodeProposal** — On-chain proposal to mutate graph topology. Types: ADD_NODE, REMOVE_NODE, ADD_EDGE, UPDATE_META. (`evolution/proposal.py`)

- **ProposalStatus** — DRAFT, SUBMITTED, VOTING, ACCEPTED, REJECTED, INTEGRATING, LIVE, BOND_RETURNED. (`evolution/proposal.py`)

- **Bond / TAO Bond** — Proposer locks TAO (minimum: `PROPOSAL_MIN_BOND_TAO`) to submit a node proposal. Returned on successful integration; burned on rejection or collapse. (`evolution/proposal.py`, `evolution/nla_settlement.py`)

- **VoteChoice** — FOR, AGAINST, ABSTAIN. (`evolution/voting.py`)

- **VotingEngine** — Tallies stake-weighted votes at epoch end. Quorum: `total_participating ≥ VOTING_QUORUM_RATIO × total_stake`. Pass: `for_weight / total_participating ≥ VOTING_PASS_RATIO`. (`evolution/voting.py`)

- **TallyResult** — for_weight, against_weight, abstain_weight, total_participating, quorum_met, passed. (`evolution/voting.py`)

### Integration (3-Phase Ramp-In)

- **FORESHADOW** — Miners receive advance notice; can pre-load embeddings/corpus. (`evolution/integration.py`)

- **BRIDGE** — Node added to graph with edge_weight = 0. Traversals can route but scores not yet committed. (`evolution/integration.py`)

- **RAMP** — Edge weight grows linearly from 0 to 1 over `INTEGRATION_BLOCKS`. (`evolution/integration.py`)

- **IntegrationState** — Tracks integration progress: proposal_id, node_id, phase, accepted_block, bridge_block, ramp_start_block, ramp_end_block, current_score. (`evolution/integration.py`)

### Pruning (3-Phase Decay)

- **HEALTHY** — Mean score ≥ `WARNING_THRESHOLD`. (`evolution/pruning.py`)

- **WARNING** — Mean score falls below `WARNING_THRESHOLD`. (`evolution/pruning.py`)

- **DECAYING** — Consecutive epochs below `DECAY_THRESHOLD`; aggressive edge decay applied. (`evolution/pruning.py`)

- **COLLAPSED** — Consecutive DECAYING epochs ≥ `DEFAULT_COLLAPSE_CONSECUTIVE`; node removed from graph. (`evolution/pruning.py`)

- **ScoreWindow** — Rolling window of `EpochScore` records. Computes mean, trend (linear slope), consecutive_below, total_traversals. (`evolution/pruning.py`)

- **EpochScore** — Score record for one node in one epoch: epoch, node_id, score, traversal_count. (`evolution/pruning.py`)

- **Drift Detection** — If a node's declared centroid drifts > `DRIFT_MAX_COSINE_DISTANCE` (0.35) from actual corpus, trigger re-incubation. (`subnet/config.py`)

---

## Unified Miner

- **Miner** — Unified Bittensor miner serving both `KnowledgeQuery` (corpus retrieval via numpy + Merkle proofs) and `NarrativeHop` (LLM-driven passage generation via OpenRouter) from a single axon. (`domain/unified_miner.py`)

- **Corpus** — Collection of text documents chunked with overlap, embedded via sentence-transformers, stored in-memory as numpy arrays. No vector DB. (`domain/corpus.py`)

- **CorpusLoader** — Loads `.txt`/`.md` from a directory, chunks with overlap, embeds, pickle-caches. (`domain/corpus.py`)

- **Chunk** — Contiguous text segment from corpus. Fields: id, source_id, text, SHA-256 hash, 768-dim embedding, char_start, char_end. (`domain/corpus.py`)

- **MerkleProver** — Constructs SHA-256 binary Merkle tree over chunk hashes. Methods: `root()`, `prove(chunk_index)`, `verify(proof, expected_root)`. (`domain/corpus.py`)

- **Merkle Root** — SHA-256 root of the binary Merkle tree over all chunk hashes. Committed on-chain via `subtensor.set_commitment()`. (`domain/corpus.py`, `domain/manifest.py`)

- **Merkle Proof** — Cryptographic proof that a chunk belongs to a corpus (identified by Merkle root). Returned in `KnowledgeQuery` responses; validated by validator and gateway. (`domain/corpus.py`, `subnet/protocol.py`)

- **Corpus** — Collection of text documents chunked with overlap, embedded via sentence-transformers, stored in-memory as numpy arrays. No vector DB. (`domain/corpus.py`)

- **CorpusLoader** — Loads `.txt`/`.md` from a directory, chunks with overlap, embeds, pickle-caches. (`domain/corpus.py`)

- **Chunk** — Contiguous text segment from corpus. Fields: id, source_id, text, SHA-256 hash, 768-dim embedding, char_start, char_end. (`domain/corpus.py`)

- **MerkleProver** — Constructs SHA-256 binary Merkle tree over chunk hashes. Methods: `root()`, `prove(chunk_index)`, `verify(proof, expected_root)`. (`domain/corpus.py`)

- **Merkle Root** — SHA-256 root of the binary Merkle tree over all chunk hashes. Committed on-chain via `subtensor.set_commitment()`. (`domain/corpus.py`, `domain/manifest.py`)

- **Merkle Proof** — Cryptographic proof that a chunk belongs to a corpus (identified by Merkle root). Returned in `KnowledgeQuery` responses; validated by validator and gateway. (`domain/corpus.py`, `subnet/protocol.py`)

- **DomainManifest** — Miner's IPFS-pinned declaration of their knowledge domain. Fields: spec_version, node_id, display_label, domain, narrative_persona, narrative_style, adjacent_nodes, centroid_embedding_cid, corpus_root_hash, chunk_count, min_stake_tao, created_at_epoch, miner_hotkey, manifest_cid. (`domain/manifest.py`)

- **Domain Centroid** — Mean embedding of all chunk embeddings in a corpus (768-dim vector). Used in groundedness scoring and drift detection. (`domain/corpus.py`, `subnet/reward.py`)

- **Domain Similarity** — Cosine similarity between query embedding and domain centroid. Self-reported by domain miner; re-verified by validator. (`subnet/reward.py`, `subnet/protocol.py`)

- **Embedding / EmbeddingVec** — 768-dimensional float vector from sentence-transformers (`all-mpnet-base-v2`). Used for relevance, coherence, groundedness, and drift detection. (`subnet/protocol.py`, `orchestrator/embedder.py`)

---

## Narrative Generation

- **Narrative Passage** — LLM-generated text describing a hop (100–500 words, second-person present tense). (`domain/unified_miner.py`, `subnet/config.py`)

- **Passage Embedding** — 768-dim embedding of the narrative passage. Used in coherence and groundedness scoring. (`subnet/protocol.py`, `subnet/reward.py`)

- **Knowledge Synthesis** — 1–3 sentence summary synthesizing retrieved chunks (max 600 chars). Scored for groundedness. (`subnet/protocol.py`)

- **Persona** — Narrative voice applied to hop generation. Options: Neutral, Scholar, Storyteller, Journalist, Explorer. Stored in node metadata; forwarded to LLM prompt. (`domain/narrative/prompt.py`)

- **Session Store** — Redis-backed (with in-memory fallback) storage for session context across hops: player_path, path_embeddings, prior_narrative. (`domain/narrative/session_store.py`)

- **OpenRouter** — OpenAI-compatible LLM API provider for narrative generation. Default model: `anthropic/claude-3.5-haiku`. Set via `OPENROUTER_API_KEY`. (`domain/unified_miner.py`, `subnet/config.py`)

---

## Orchestrator & Gateway

- **Orchestrator** — FastAPI gateway managing session lifecycle. Endpoints: `POST /enter`, `POST /hop`, `GET /session/{id}`, `WS /session/{id}/live`, `GET /graph/*`, `GET /healthz`. (`orchestrator/gateway.py`)

- **OrchestratorSession** — Manages one player's traversal: `enter()` → `hop()` → `hop()` → ... Tracks session_id, state, player_path, path_embeddings, prior_narrative, current_node_id, choice_cards. (`orchestrator/session.py`)

- **SessionState** — CREATED, ACTIVE, TERMINAL, ERROR. (`orchestrator/session.py`)

- **Router** — Ranks entry-node candidates by domain similarity to query. Resolves narrative miner for destination node. (`orchestrator/router.py`)

- **PathSafetyGuard** — Prevents cycles (no revisiting recent nodes), enforces max hops per session (`ORCHESTRATOR_MAX_HOPS`), enforces word count limits. (`orchestrator/safety_guard.py`)

- **TraversalArbiter** — Calls Arkhai NLA to arbitrate hop validity and filter next-hop candidates. Returns approved/rejected + filtered candidate list. (`orchestrator/arbiter.py`)

- **HopArbiterResult** — Result from Arkhai traversal arbiter: approved, filtered_candidates, reasoning, arbiter_uid. (`orchestrator/arbiter.py`)

- **Embedder** — Wraps sentence-transformers (`all-mpnet-base-v2`) for query/passage embedding in the gateway. (`orchestrator/embedder.py`)

- **Enter / Entry Point** — First hop: player submits `query_text`, gateway embeds it, resolves best-matching node. (`orchestrator/gateway.py`)

---

## External Integrations

- **Unbrowse.ai** — Live web context fallback when corpus similarity < `UNBROWSE_CORPUS_THRESHOLD` (0.35). Domain miners fetch web snippets to supplement responses; narrative miners inject web context into LLM prompts. Also validates real-world coverage for new node proposals. (`orchestrator/unbrowse.py`, `subnet/config.py`)

- **UnbrowseResult** — Result from Unbrowse query: success flag + list of text snippets. (`orchestrator/unbrowse.py`)

- **Arkhai / Alkahest** — On-chain settlement platform for governance bonds via EAS-based escrow. Provides NLA endpoint for traversal arbitration. Bond returned if node reaches LIVE; burned if rejected/collapsed. (`evolution/nla_settlement.py`, `orchestrator/arbiter.py`)

- **NLA (Natural Language Agreement)** — Arkhai protocol for escrow and on-chain attestation. Used for bond settlement and traversal arbitration. (`evolution/nla_settlement.py`)

- **StringObligation** — Arkhai schema for natural language obligations (e.g., traversal demand). (`orchestrator/arbiter.py`)

---

## Frontend & Visualization

- **Bonfires** — Knowledge network visualization metaphor. Nodes as burning sites, edges as paths between them. Three entity types: Entities (nodes), Edges, Episodes (traversals). (`src/lib/server/bonfires.ts`)

- **BonfireEntity** — UI representation of a node: uuid, name, node_type, labels, summary, created_at. (`src/lib/server/bonfires.ts`)

- **BonfireEdge** — UI representation of an edge: uuid, edge_type, source_node_uuid, target_node_uuid, fact, weight. (`src/lib/server/bonfires.ts`)

- **BonfireEpisode** — UI representation of a traversal: uuid, name, content, created_at. (`src/lib/server/bonfires.ts`)

- **Delve** — Deep-dive request into a node's neighbors and adjacent edges. (`src/lib/api/schemas.ts`, `src/lib/server/bonfires.ts`)

- **Expand** — Expand a node's neighborhood in graph visualization. (`src/lib/api/schemas.ts`)

- **Force Layout** — 3D force-directed graph layout engine with Barnes-Hut octree for O(n log n) node repulsion + spring physics for edge attraction. (`src/lib/components/graph/force-layout.ts`)

- **LayoutNode / LayoutLink** — Node and link representations in force layout simulation. Position (3D), velocity, acceleration, mass, radius. (`src/lib/components/graph/force-layout.ts`)

- **Octree** — Barnes-Hut octree for efficient N-body force computation. Divides 3D space into 8 children; far nodes treated as single mass center. (`src/lib/components/graph/octree.ts`)

- **Spring3D** — Spring simulation connecting nodes with rest_length and attractive force. (`src/lib/components/graph/spring.ts`)

- **GraphScene / GraphCanvas** — Svelte components for 3D graph rendering using Threlte + Three.js. (`src/lib/components/graph/GraphScene.svelte`, `GraphCanvas.svelte`)

---

## Configuration

- **AXON_ Prefix** — Environment variables override subnet config constants. Example: `AXON_TRAVERSAL_WEIGHT=0.5` overrides `TRAVERSAL_WEIGHT`. (`subnet/config.py`)

- **SubnetConfig** — Snapshot class of all subnet constants at import time. Convenience wrapper for passing config as a single object. (`subnet/config.py`)

- **KuzuDB** — Embedded graph database for persistent storage (optional). Replaces in-memory graph for validators/gateways with PVC. (`subnet/graph_store.py`)

- **MetagraphWatcher** — Async background poller with `AxonCache`. Fires `RegistrationEvent` callbacks on miner changes. (`subnet/metagraph_watcher.py`)

- **AxonCache** — Cache of known axon endpoints, maintained by `MetagraphWatcher`. (`subnet/metagraph_watcher.py`)

---

## Graph Infrastructure

- **_MemoryGraph** — Thread-safe in-process graph with adjacency lists. Methods: add_node, get_node, upsert_edge, reinforce_edge, decay_all, neighbours, outgoing_edge_weight_sum, record_traversal. (`subnet/graph_store.py`)

- **GraphStore** — Wrapper around `_MemoryGraph` with optional KuzuDB persistence. Primary interface for all graph operations. (`subnet/graph_store.py`)

---

## Kubernetes Resources

- **Gateway** — HPA (2–5 replicas). FastAPI orchestrator deployment. (`k8s/`)
- **Validator** — StatefulSet + PVC. Runs scoring and weight-setting. (`k8s/`)
- **Miner** — Deployment serving KnowledgeQuery and NarrativeHop from unified miner. (`k8s/`)
- **Frontend** — SvelteKit web app deployment. (`k8s/`)
- **Redis** — Session store backend. (`k8s/`)
- **IPFS** — Manifest and centroid embedding storage. (`k8s/`)
