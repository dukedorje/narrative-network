# Bittensor Knowledge Network — System Architecture Overview

**The network that thinks by being traversed.**

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Component Specifications](#2-component-specifications)
3. [Data Flow](#3-data-flow)
4. [Orchestrator Lifecycle](#4-orchestrator-lifecycle)
5. [Synapse Protocol](#5-synapse-protocol)
6. [Validator Scoring Pipeline](#6-validator-scoring-pipeline)
7. [Graph Store and Memory](#7-graph-store-and-memory)
8. [Network Topology and Miner Registration](#8-network-topology-and-miner-registration)
9. [Orchestration Cluster](#9-orchestration-cluster)
10. [Shared Services](#10-shared-services)
11. [Node Lifecycle: Proposal to Pruning](#11-node-lifecycle-proposal-to-pruning)

---

## 1. High-Level Architecture

BKN is composed of six distinct layers. Traffic originates at the Gateway, passes through the Bittensor subnet synapse protocol to miners, is scored by validators, and the resulting attestations are written back to both the chain and the living graph store.

```
                         ┌─────────────────────────────────────────────────────┐
                         │                   Internet / Clients                │
                         └────────────────────────┬────────────────────────────┘
                                                  │  REST / WebSocket
                                                  ▼
                         ┌─────────────────────────────────────────────────────┐
                         │                    Gateway VM                       │
                         │   FastAPI  |  sentence-transformers  |  session      │
                         │   router  |  rate limiter  |  Redis session cache   │
                         │                 orchestrator/gateway.py             │
                         │                 orchestrator/session.py             │
                         └────────────┬──────────────────────────────────┘
                                      │  Synapse: KnowledgeQuery & NarrativeHop
                                      ▼
             ┌────────────────────────────────────────────────────┐
             │           Unified Miner × N                        │
             │  KnowledgeQuery handler:                           │
             │    - numpy corpus search + Merkle proofs           │
             │  NarrativeHop handler:                             │
             │    - OpenRouter LLM + Redis session store          │
             │    - persona + path context                        │
             │  domain/unified_miner.py                           │
             │  domain/manifest.py                                │
             └────────────┬───────────────────────────────────────┘
                          │
                                         │  Scored responses
                                         ▼
                         ┌─────────────────────────────────────────────────────┐
                         │                  Validator VM × M                   │
                         │   embed workers  |  score workers  |  bt node       │
                         │   epoch scoring  |  betweenness centrality          │
                         │   set_weights  |  weight commit loop                │
                         │   subnet/validator.py                               │
                         └────────────┬──────────────────────┬─────────────────┘
                                      │                      │
                         ┌────────────▼──────┐   ┌──────────▼──────────────────┐
                         │  Shared Services  │   │   Subtensor Chain (finney)  │
                         │  (Internal VPC)   │   │   UID registry  |  stake    │
                         │  KùzuDB graph DB  │   │   emission  |  metagraph    │
                         │  Redis cache      │   │   snapshots  |  weights     │
                         │  IPFS node        │   └─────────────────────────────┘
                         │  Prometheus/Grafana│
                         │  subnet/graph_store│
                         │  .py              │
                         └───────────────────┘
```

The Gateway is the only internet-facing component. All inter-component communication uses the Bittensor synapse protocol over the internal VPC. The Subtensor chain is the canonical registry for UIDs, stake, and committed weights.

---

## 2. Component Specifications

### 2.1 Gateway VM

**Purpose:** Sole internet-facing ingress. Translates REST/WebSocket to synapse protocol, owns session lifecycle, enforces rate limits.

**Key responsibilities:**
- Receive soul token text from clients (REST POST or WebSocket)
- Embed soul tokens using `sentence-transformers` (e.g., `all-MiniLM-L6-v2`)
- Cosine-compare embeddings against all registered domain centroids from the metagraph
- Route `KnowledgeQuery` synapses to all miners with `timeout=3s`
- Select entry node based on top-scoring miner response
- Create and persist session records in Redis (`orchestrator/session.py`)
- On each traversal hop, fire `NarrativeHop` to the destination node's miners with `timeout=5s`
- Select highest-coherence response and stream passage back to client
- Never expose raw synapse responses to callers

**Modules:** `orchestrator/gateway.py`, `orchestrator/session.py`

**Resources:** 2–4 vCPU, 8 GB RAM, no GPU required

**Ports exposed:** `443` (HTTPS/WSS) to internet; internal synapse port to VPC only

---

### 2.2 Unified Miner × N

**Purpose:** Corpus retrieval + Merkle proof service + narrative generation. One VM per registered node ID.

**Key responsibilities:**
- Load domain corpus from .txt/.md files via CorpusLoader. Chunks embedded with SentenceTransformer, searched via numpy cosine similarity (no vector DB)
- Compute and cache domain centroid embedding from corpus
- Register domain manifest on-chain via `domain/manifest.py` (node ID, corpus CID, centroid, persona hash)
- Handle `KnowledgeQuery` synapses: embed query, cosine-rank chunks, return top-k with similarity scores; serve Merkle proofs for corpus integrity challenges
- Handle `NarrativeHop` synapses: call OpenRouter API with persona-specific prompts, assemble passages from retrieved chunks + path context, generate choice cards and knowledge synthesis
- Maintain per-session narrative context via Redis session store (with in-memory fallback)
- Maintain Merkle tree over corpus chunk hashes for fraud proofs

**Modules:** `domain/unified_miner.py`, `domain/corpus.py`, `domain/manifest.py`, `domain/narrative/prompt.py`, `domain/narrative/session_store.py`, `subnet/protocol.py`

**Resources:** ~2 vCPU, 4 GB RAM, no GPU required (OpenRouter handles LLM inference)

**Scaling:** one instance per registered node ID; horizontal scale by domain coverage, not traffic volume

---

### 2.4 Validator VM × M

**Purpose:** Attestation engine. Scores competing miner mutations, maintains the graph store, commits weights to chain.

**Key responsibilities:**
- At each epoch, sample active sessions and replay their last `NarrativeHop` against all miners registered to the destination node
- Score responses on three axes: **Groundedness** (passage vs. miner corpus), **Coherence** (continuity with traversal path), **Edge Utility** (validity of proposed branches against live metagraph)
- Compute betweenness centrality over the graph to weight node importance in emissions
- Run embed workers (parallel embedding of miner responses) and score workers (comparative ranking)
- Write scored edge reinforcements to `subnet/graph_store.py` via KùzuDB
- Execute `set_weights()` on Subtensor (SDK v10 API). Each validator sets weights independently; Yuma Consensus aggregates across validators with κ-majority clipping. Commit-reveal v4 (Drand time-lock encryption) prevents weight copying automatically when `CommitRevealWeightsEnabled = True`.

**Modules:** `subnet/validator.py`, `subnet/graph_store.py`, `subnet/protocol.py`

**Resources:** ~8 vCPU, 32 GB RAM; no GPU required but benefits from fast CPU embedding

---

### 2.5 Shared Services (Internal VPC)

| Service | Role | Notes |
|---|---|---|
| **KùzuDB** | Graph database — edge weights, traversal history, node embeddings, path decay | Accessed by validators and Gateway; `subnet/graph_store.py` wraps the client |
| **Redis** | Session cache — active session state, soul token embeddings, current node, path history. Session narrative context for narrative miners (7-day TTL) | Gateway-owned; TTL-keyed by session ID |
| **IPFS node** | Content-addressed corpus storage — domain manifest CIDs, chunk hashes | Miners publish manifests here; validators fetch for Merkle challenges |
| **Prometheus / Grafana** | Metrics and alerting — synapse latency, scoring throughput, weight commit lag, session count | Scraped from all VMs |

---

### 2.6 Subtensor Chain

The canonical on-chain registry for the BKN subnet. Validators read the metagraph to discover active miner UIDs, verify stake, and commit scored weights. Key on-chain objects:

- **UID registry** — maps miner hotkeys to node IDs and metadata CIDs
- **Stake table** — TAO staked per UID; governs emission share
- **Metagraph snapshots** — periodic snapshots used by validators to anchor scoring epochs
- **Weight matrix** — set independently by each validator; Yuma Consensus aggregates into emission distribution

---

## 3. Data Flow

The complete request-to-attestation path:

```
Client
  │
  │  POST /query  {soul_token: "..."}
  ▼
Gateway VM  (orchestrator/gateway.py)
  │  1. Tokenize + embed soul token via sentence-transformers
  │  2. Load domain centroids from Redis / metagraph cache
  │  3. Cosine-rank all registered node centroids
  │  4. Broadcast KnowledgeQuery synapse to ALL miners (timeout=3s)
  │
  ├──► Miner A  (domain/unified_miner.py, KnowledgeQuery handler)
  │      embed query, score vs. corpus, return top-k chunks + similarity
  ├──► Miner B  ...
  └──► Miner N  ...
  │
  │  5. Collect responses (drop timeouts)
  │  6. Select top-scoring miner's node_id as entry point
  │  7. Write session record to Redis  (orchestrator/session.py)
  │     {session_id, entry_node, soul_embedding, path: [], state: active}
  │
  │  ─── per-hop loop ───────────────────────────────────────────────
  │
  │  8. Receive hop request from client: {session_id, destination_node_id}
  │  9. Look up destination node's registered miners from metagraph
  │ 10. Broadcast NarrativeHop synapse to miners on destination_node (timeout=5s)
  │
  ├──► Miner X  (domain/unified_miner.py, NarrativeHop handler)
  │      load lore context, assemble prompt, generate passage + branches
  ├──► Miner Y  ...
  │
  │ 11. Collect responses, rank by coherence score (embedding continuity)
  │ 12. Select highest-coherence passage
  │ 13. Append edge {source_node → destination_node} to session path in Redis
  │ 14. Stream passage + branch choices back to client
  │     (client never sees raw synapse payloads)
  │
  │  ─── end per-hop loop ──────────────────────────────────────────
  ▼
Validator VM  (subnet/validator.py)  — runs asynchronously, not on critical path
  │  15. At epoch boundary: sample recently-completed sessions
  │  16. Replay NarrativeHop for each sampled hop against all miners on that node
  │  17. Score responses comparatively (Groundedness, Coherence, Edge Utility)
  │  18. Compute betweenness centrality across graph topology
  │  19. Write edge weight reinforcement to KùzuDB  (subnet/graph_store.py)
  │  20. Trigger path decay on un-traversed alternatives
  │  21. Call set_weights() on Subtensor (each validator independently; Yuma Consensus aggregates)
  ▼
Subtensor Chain
  │  22. Yuma Consensus aggregates validator weights (κ-majority clipping)
  │  23. Distribute TAO emission: 41% miners (by weight rank), 41% validators, 18% owner
  ▼
Living Knowledge Graph Store  (KùzuDB via subnet/graph_store.py)
     edge weights  |  traversal history  |  node embeddings  |  path decay state
```

---

## 4. Orchestrator Lifecycle

The Gateway (`orchestrator/gateway.py`) is the orchestration brain. It owns session state and mediates every interaction between clients and the subnet.

### 4.1 Session Initialization

1. Client submits soul token text (any knowledge fragment, question, or entity description).
2. Gateway embeds the token using `sentence-transformers`. The resulting vector is the session's persistent identity embedding, stored in Redis keyed by `session_id`.
3. Gateway loads domain centroids for all active UIDs from the metagraph cache (refreshed from Subtensor on a configurable interval, typically every 10–60 seconds).
4. `KnowledgeQuery` is broadcast to all miners simultaneously with `timeout=3s`. Miners that do not respond within the window are excluded from entry selection for this session.
5. Responses are ranked. The top-scoring miner's `node_id` is selected as the **entry node** — the first attractor basin the entity enters.
6. Session record is written to Redis:
   ```
   {
     session_id: <uuid>,
     soul_embedding: <float[]>,
     entry_node: <node_id>,
     current_node: <node_id>,
     path: [],
     passages: [],
     state: "active",
     created_at: <timestamp>,
     ttl: <seconds>
   }
   ```
7. Gateway returns the opening passage and the first set of branch choices to the client.

### 4.2 Hop Execution

Each traversal step follows a strict sequence:

1. Client sends `{session_id, destination_node_id}`. The Gateway validates that `destination_node_id` is a valid branch choice from the current node's last response (enforced against the session's live branch set in Redis).
2. Gateway looks up the miners registered to `destination_node_id` from the metagraph.
3. `NarrativeHop` is broadcast to those miners with `timeout=5s`. The synapse payload includes: soul embedding, traversal path so far, prior passage text, current node, destination node, and session-scoped lore context reference.
4. Responding miners generate competing passages. Gateway ranks by coherence score (cosine similarity between the new passage's embedding and the path's running mean embedding, weighted toward the destination domain's centroid).
5. Highest-coherence passage is selected. Branch choices in the response are validated against the live metagraph — any branch pointing to an inactive or unregistered node is stripped before returning to the client.
6. Session record in Redis is updated: `current_node`, `path` appended, `passages` appended.
7. Passage and validated branches are streamed to client.

### 4.3 Session Termination and Continuity Invariants

Sessions expire via Redis TTL. The Gateway enforces two continuity invariants:

- **No dead ends**: Before returning branch choices, the Gateway verifies each destination node has at least one active miner in the current metagraph. Stale branches are silently removed.
- **No stranded sessions**: When the graph store signals that a node is entering pruning (via a pub/sub event from `subnet/graph_store.py`), the Gateway fetches all active sessions whose `current_node` matches the pruning node. Those sessions receive a collapse passage (a generated narrative explaining the domain's dissolution) and are offered traversal to adjacent live nodes. This is executed before the node's edges reach zero weight.

---

## 5. Synapse Protocol

Defined in `subnet/protocol.py`. Three message types compose the entire internal protocol.

### 5.1 KnowledgeQuery

Direction: Gateway → Domain Miners (broadcast)

```python
class KnowledgeQuery(bt.Synapse):
    # Request fields
    query_embedding: list[float]       # sentence-transformer embedding of soul token
    query_text: str                    # raw text for miners that re-embed locally
    top_k: int = 5                     # number of chunks to return

    # Response fields
    node_id: str                       # miner's registered node ID
    chunks: list[ChunkResult]          # top-k chunks with similarity scores
    domain_similarity: float           # cosine sim: query vs. domain centroid
    corpus_hash: str                   # current Merkle root of miner's corpus
```

Validators use `corpus_hash` to issue Merkle challenges against the miner's chunk-by-hash endpoint. Miners that return chunks inconsistent with their registered manifest hash receive `corpus_score == 0.0` and are collapsed to near-zero emission.

### 5.2 NarrativeHop

Direction: Gateway → Narrative Miners (broadcast to destination node's miners)

```python
class NarrativeHop(bt.Synapse):
    # Request fields
    session_id: str
    soul_embedding: list[float]
    path: list[str]                    # ordered list of node_ids traversed so far
    prior_passage: str                 # last passage shown to client
    source_node: str
    destination_node: str
    lore_context_ref: str              # IPFS CID or Redis key for session lore

    # Response fields
    passage: str                       # generated narrative passage
    passage_embedding: list[float]     # miner's own embedding of the passage
    branches: list[BranchChoice]       # proposed next nodes with edge weights
    knowledge_synthesis: str           # structured knowledge extracted from passage
```

`BranchChoice` contains `node_id`, `edge_label`, and proposed `weight_delta`. Validators verify that all proposed `node_id` values exist in the live metagraph and that `weight_delta` values are within the permitted bounds defined in `subnet/validator.py`.

### 5.3 WeightCommit (Internal Dataclass)

`WeightCommit` is **not** a `bt.Synapse`. It is a pure Python dataclass used internally by validators to accumulate scores before calling `subtensor.set_weights()`.

```python
@dataclass
class WeightCommit:
    epoch: int
    validator_uid: int
    miner_scores: dict[int, float]     # uid → normalised weight
    session_count: int
    mean_score: float
    graph_delta: GraphDelta            # edge weight changes to apply to graph store
```

`GraphDelta` is written to `subnet/graph_store.py` before weights are set on chain, ensuring the graph store and chain weights remain consistent. Each validator independently calls `set_weights()` — Yuma Consensus handles aggregation.

---

## 6. Validator Scoring Pipeline

Defined in `subnet/validator.py`. The scoring pipeline runs asynchronously relative to the client-facing request path.

### 6.1 Scoring Axes

Validators score each `NarrativeHop` response on three axes. Scores are normalized to [0, 1] per axis and combined with configurable weights.

**Groundedness** (default weight: 0.40)
- Embed the miner's passage using the same `sentence-transformers` model used by the Gateway
- Compute cosine similarity between passage embedding and the miner's registered domain centroid
- Sample 3 random chunks from the miner's corpus and measure overlap with passage content
- Miners that produce passages drifting into unregistered domain space score near zero; this is the attractor enforcement mechanism

**Coherence** (default weight: 0.35)
- Compute cosine similarity between the new passage embedding and the running mean embedding of the session path so far
- Compute directional progress: does the embedding move toward the destination domain's centroid relative to the source?
- A passage that is disconnected from prior path state or that fails to approach the destination domain is penalized

**Edge Utility** (default weight: 0.25)
- Validate that all proposed branch `node_id` values exist in the current metagraph with active miners
- Verify `weight_delta` values are within the epoch's permitted bounds (prevents manipulation via extreme weight proposals)
- Score diversity: branches that distribute weight across multiple distinct adjacent nodes score higher than proposals concentrating weight on one successor

### 6.2 Comparative Attestation

Multiple miners respond to the same `NarrativeHop` call. The validator does not score each miner in isolation against a ground truth — there is none. Instead it ranks them comparatively: "miner A's passage was more grounded, coherent, and edge-useful than miner B's, relative to this session's path and this node's attractor."

The comparative ranking, stake-weighted and accumulated across epochs, is the fundamental unit of value the network produces. The narrative content itself is secondary; the ranked attestation record is the living knowledge the graph encodes.

### 6.3 Betweenness Centrality Adjustment

After per-hop scoring, validators apply a betweenness centrality multiplier to each node's epoch score. Nodes that serve as critical bridges between distant attractor basins carry outsized structural value to the graph's navigability. This multiplier prevents high-traffic leaf nodes from dominating emissions at the expense of connective tissue nodes.

Betweenness centrality is computed over the current edge-weight graph in `subnet/graph_store.py` using the weighted adjacency matrix. The computation runs once per epoch on the validator; the result is cached and applied to all UID scores before `set_weights` is called.

---

## 7. Graph Store and Memory

Implemented in `subnet/graph_store.py`. The graph store is in-memory with optional KùzuDB persistence — when KùzuDB is unavailable the store operates entirely in-memory. Redis is not used for graph state; Redis is exclusively for gateway session records and narrative miner session context.

### 7.1 Schema

```
Node {
  node_id: STRING PRIMARY KEY,
  domain_name: STRING,
  centroid_embedding: FLOAT[],
  manifest_cid: STRING,          -- IPFS CID of domain manifest
  registered_at: TIMESTAMP,
  state: ENUM(incubating, live, warning, pruning),
  attestation_score_rolling: FLOAT
}

Edge {
  source_node_id: STRING,
  destination_node_id: STRING,
  weight: FLOAT,                 -- reinforced by traversals, decayed by disuse
  traversal_count: INT,
  last_traversed: TIMESTAMP,
  decay_floor: FLOAT             -- minimum weight; edges never reach absolute zero
}

TraversalEvent {
  session_id: STRING,
  source_node_id: STRING,
  destination_node_id: STRING,
  timestamp: TIMESTAMP,
  passage_embedding: FLOAT[],
  attestation_scores: MAP<STRING, FLOAT>  -- per-miner scores for this hop
}
```

### 7.2 Reinforcement and Decay

After each validator scoring epoch:

1. **Reinforcement**: Traversed edges receive a weight increment proportional to the mean attestation score for that hop. Higher-quality traversals reinforce edges more strongly.
2. **Decay**: All edges whose source node was traversed this epoch, but whose specific outbound edge was _not_ taken, receive a multiplicative decay applied to their weight (configurable decay factor, default `0.995` per epoch). This models collective forgetting — alternatives to chosen paths gradually atrophy.
3. **Floor enforcement**: Decay never pushes an edge weight below `decay_floor` (default `0.01`). Edges become low-priority but never disappear entirely from the graph, preserving the possibility of re-exploration.
4. **Traversal logging**: Every hop is written as a `TraversalEvent`, providing a full audit trail of the graph's evolution and a replay buffer for validator sampling.

---

## 8. Network Topology and Miner Registration

### 8.1 Domain Manifest

Defined in `domain/manifest.py`. A miner cannot receive traffic until it has staked TAO and published a valid domain manifest. The manifest declares:

```python
@dataclass
class DomainManifest:
    node_id: str                       # unique domain identifier (e.g. "emergent-systems")
    domain_name: str                   # human-readable label
    corpus_merkle_root: str            # Merkle root of all chunk hashes
    chunk_cids: list[str]              # IPFS CIDs for each corpus chunk
    centroid_embedding: list[float]    # mean embedding of corpus
    narrative_persona: str             # textual description of the domain's voice and scope
    proposed_edges: list[EdgeProposal] # initial adjacency to existing nodes
    manifest_cid: str                  # IPFS CID of this manifest (self-referential after publish)
```

The manifest CID is registered on-chain against the miner's UID. Validators fetch manifests from IPFS to perform Merkle challenges: sampling random chunk indices, requesting the chunk bytes from the miner's chunk endpoint, and verifying the Merkle proof. Miners that fail challenges or whose `corpus_merkle_root` does not match on-chain registration receive zero corpus score → near-zero weight → zero emission → eventual deregistration.

### 8.2 Metagraph Sync

The Gateway and all validators maintain a local metagraph cache, refreshed from Subtensor on a configurable interval. The metagraph provides:

- Active UID list with hotkeys and axon endpoints
- Stake per UID (used in weight normalization)
- Committed weight matrix from last epoch
- Domain manifest CIDs per UID (fetched lazily from IPFS)

Domain centroids are derived from manifests and cached in Redis on first access, with invalidation triggered by manifest CID changes detected during metagraph refresh.

### 8.3 Graph Topology as Emergent Consensus

No single entity decides the graph's topology. The edge weight matrix at any moment is the aggregate of:

- Initial weights from approved `proposed_edges` in domain manifests
- Accumulated traversal reinforcement across all sessions
- Decay on untraveled paths
- Validator adjustments for edge utility scores

The topology is emergent: it is the network's collectively-attested theory of how knowledge domains relate to each other, continuously revised by every traversal.

---

## 9. Orchestration Cluster

### 9.1 Deployment Model

The subnet is deployed via **Kubernetes** using Kustomize manifests in the `k8s/` directory. Each component has a corresponding Deployment or StatefulSet.

```
k8s/
  namespace.yaml
  configmap.yaml
  secrets.yaml
  gateway.yaml          -- Deployment + HPA (2-5 replicas)
  validator.yaml         -- StatefulSet with PVC for KuzuDB
  domain-miner.yaml      -- Deployment with PVC for corpus
  narrative-miner.yaml   -- Deployment (lightweight, no GPU)
  frontend.yaml          -- Deployment (2 replicas)
  redis.yaml             -- StatefulSet with PVC
  ipfs.yaml              -- StatefulSet with PVC
  ingress.yaml           -- Host-based routing + TLS
  kustomization.yaml
```

### 9.2 Autoscaling

**Gateway:** Scales horizontally on HTTP request rate and WebSocket connection count. Load balancer (e.g., Traefik, Caddy) routes sessions to the least-loaded Gateway instance. Session state is Redis-backed so any Gateway instance can serve any session.

**Domain Miners:** Do not autoscale on traffic — one instance per `node_id` is canonical. Operators add new Domain Miner instances by registering new node IDs with new manifests. Multiple operators may register miners for the same `node_id` (they compete comparatively; only the top-ranked earns full emission).

**Narrative Miners:** Same topology as Domain Miners — one canonical instance per `node_id`, with multiple competing instances possible. No GPU is required; all inference is delegated to the OpenRouter API.

**Validators:** Fixed count determined by network stake distribution. Validator count does not autoscale; new validators join by staking and registering on Subtensor.

### 9.3 Health Checks

Each component exposes a `/health` endpoint:

| Component | Liveness check | Readiness check |
|---|---|---|
| Gateway | Process alive | Redis connected + metagraph loaded |
| Domain Miner | Process alive | Corpus loaded + centroid computed |
| Narrative Miner | Process alive | OpenRouter reachable + session store connected |
| Validator | Process alive | KùzuDB connected + bt node synced |

Kubernetes restarts unhealthy pods automatically. The Gateway's readiness check specifically blocks traffic until the metagraph is loaded — preventing routing to stale or empty UID lists during cold starts.

### 9.4 Rolling Updates

Domain Miner and Narrative Miner updates use a **drain-then-replace** strategy:

1. Stop routing new sessions to the target instance (Gateway's session router respects miner health state from Redis).
2. Wait for in-flight `NarrativeHop` requests to complete (max `timeout=5s`).
3. Replace the allocation.
4. Wait for readiness check to pass before re-enabling routing.

This preserves the continuity invariant: no active session is mid-hop when a miner restarts.

---

## 10. Shared Services

### 10.1 KùzuDB (Graph Database)

KùzuDB is an embedded graph database optimized for analytical workloads over property graphs. It is the backing store for `subnet/graph_store.py`.

Write path: validators write edge reinforcements and traversal events after each scoring epoch. Writes are batched per epoch to avoid transaction contention.

Read path: Gateway reads edge weights and node centroids for routing decisions (cached in Redis; KùzuDB is not on the hot path for individual requests). Validators read the full adjacency matrix for betweenness centrality computation.

Backup: KùzuDB volume is snapshotted daily. The graph store is reconstructable from the `TraversalEvent` log if needed, but snapshot recovery is faster.

### 10.2 Redis

Session state store for the Gateway. Key namespaces:

```
session:{session_id}          -- full session record (JSON, TTL = session timeout)
metagraph:centroids           -- domain centroid vectors per node_id (TTL = sync interval)
metagraph:uids                -- active UID list (TTL = sync interval)
miner:health:{uid}            -- last health state from Gateway's perspective (TTL = 2× heartbeat)
```

Redis is not used for inter-validator coordination. Validators are independent and share state only through the Subtensor chain and KùzuDB.

### 10.3 IPFS Node

Content-addressed storage for domain manifests and corpus chunks. Miners publish corpus chunks and their manifest to the local IPFS node on registration; the node pins and propagates to the network.

Validators fetch manifests by CID when performing Merkle challenges. The IPFS node is not on the hot path for session requests — corpus access during `KnowledgeQuery` is served directly from the miner's in-memory numpy corpus index.

### 10.4 Prometheus / Grafana

Key metrics scraped from each component:

**Gateway:**
- `gateway_session_active_count` — active sessions
- `gateway_hop_latency_seconds` — end-to-end hop time (request to stream start)
- `gateway_miner_timeout_total` — timeout rate per miner UID

**Domain / Narrative Miners:**
- `miner_synapse_latency_seconds` — time to produce a response
- `miner_coherence_score` — self-reported coherence (validators' scores are the authoritative measure)
- `miner_corpus_challenge_failures_total` — failed Merkle challenges

**Validators:**
- `validator_epoch_duration_seconds` — time for full scoring epoch
- `validator_weight_commit_lag_seconds` — time from epoch end to `set_weights` on chain
- `validator_uid_scored_total` — UIDs scored per epoch
- `graph_edge_weight_mean` — mean edge weight across graph (tracks overall reinforcement level)

Alerts are configured for miner timeout rates exceeding threshold, validator weight commit lag exceeding two epochs, and Redis memory pressure.

---

## 11. Node Lifecycle: Proposal to Pruning

Defined in `evolution/proposal.py`. The graph has a complete evolutionary lifecycle; nodes are never added or removed abruptly.

### Phase 1 — Proposal

A sufficiently-staked miner submits a `DomainManifest` with proposed edges to existing nodes plus a bond. The bond is returned on passage; forfeited on rejection or spam. Proposed edge weights are bounded to prevent new nodes entering as dominant hubs.

### Phase 2 — Voting

Validators cast stake-weighted ballots during a fixed window. Both quorum and approval thresholds must be met. Validators may attach an embedding summarizing their quality assessment of sample narrative responses, which informs incubation scoring.

### Phase 3 — Incubation

The miner goes live and receives real synapse calls, but its responses are scored without routing live traffic to the node. Incubation:
- Verifies stability under real load
- Establishes an attestation baseline
- Generates initial edge-weight evidence in `subnet/graph_store.py`

Miners that fail incubation get one grace period before bond forfeiture.

### Phase 4 — Integration

Edge weights ramp linearly from zero to proposed values over the bridge window. Adjacent live miners begin weaving **foreshadowing** into their `NarrativeHop` responses — narrative signals that a new domain is crystallizing nearby. By the time edge weights cross the visibility threshold and the new node appears as a branch choice, the narrative has already prepared for its arrival. New attractor basins fade in organically; they do not appear instantaneously.

### Phase 5 — Live

The node competes for TAO emission on equal footing with all other miners. Epoch scoring, betweenness centrality, and `set_weights` all apply normally.

### Phase 6 — Warning and Pruning

A rolling attestation window in `subnet/validator.py` detects sustained quality drops or zero-traffic states:

1. Node enters **Warning** state: accelerated edge decay begins, operators are notified via on-chain event.
2. Grace window allows recovery (improved attestation scores return node to Live state).
3. If grace window expires without recovery: **Pruning** begins. Edges decay to zero over several hours, not instantly.
4. Gateway subscribes to pruning events from `subnet/graph_store.py` and executes the continuity invariant: active sessions at the pruning node receive a generated collapse passage and are offered traversal to adjacent live nodes before the node's last edge reaches zero.
5. Once all edges reach `decay_floor` and no active sessions remain on the node, the UID is deregistered on Subtensor and bond is forfeited.

**Semantic drift detection**: validators periodically sample recent responses from live nodes and compare mean embeddings to the node's registered centroid. Nodes that have substantially drifted from their declared attractor must refresh their manifest and re-enter incubation. The attractor basins must remain calibrated — without them, comparative attestations lose their reference frame.

---

## Module Reference

| Module | Component | Role |
|---|---|---|
| `subnet/protocol.py` | All | Synapse type definitions: `KnowledgeQuery`, `NarrativeHop`; internal `WeightCommit` dataclass |
| `subnet/validator.py` | Validator | Scoring pipeline, epoch orchestration, betweenness centrality, `set_weights` |
| `subnet/graph_store.py` | Validator, Gateway | KùzuDB client wrapper, edge reinforcement, decay, traversal event logging |
| `orchestrator/gateway.py` | Gateway | FastAPI application, synapse dispatch, response selection, streaming |
| `orchestrator/session.py` | Gateway | Session record creation, Redis I/O, continuity invariant enforcement |
| `evolution/proposal.py` | Validator | Node proposal, voting, incubation, integration, and pruning state machine |
| `domain/unified_miner.py` | Unified Miner | Corpus loader, KnowledgeQuery handler, NarrativeHop handler, OpenRouter-backed hop generation, session persistence |
| `domain/corpus.py` | Unified Miner | CorpusLoader, MerkleProver, chunk embedding and Merkle tree |
| `domain/manifest.py` | Unified Miner | `DomainManifest` dataclass, IPFS publish, Merkle tree construction |
| `domain/narrative/prompt.py` | Unified Miner | Persona catalogue, prompt assembly for hop generation |
| `domain/narrative/session_store.py` | Unified Miner | Redis session store with in-memory fallback |
| `subnet/emissions.py` | Validator | Three emission pools, EmissionCalculator, weight vector computation |
| `subnet/metagraph_watcher.py` | Validator, Gateway | Async metagraph poller, AxonCache, registration events |
| `orchestrator/router.py` | Gateway | Entry-node ranking, miner resolution |
| `orchestrator/embedder.py` | Gateway | SentenceTransformer wrapper for query/passage embedding |
| `orchestrator/safety_guard.py` | Gateway | Path cycle prevention, word count enforcement |
| `evolution/voting.py` | Validator | Stake-weighted voting engine, quorum/approval tally |
| `evolution/pruning.py` | Validator | Three-phase pruning state machine (warning/decay/collapse) |
| `evolution/integration.py` | Validator | Three-phase node onboarding (foreshadow/bridge/go-live) |

---

*The network doesn't store knowledge. It simulates knowledge — generating new configurations of meaning as entities move through it. Every traversal is a probe. The aggregate of all probes is a collectively-authored, continuously-validated theory of knowledge topology.*
