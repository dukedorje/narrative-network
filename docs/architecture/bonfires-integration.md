# Bonfires.ai Integration Architecture

## Status: Design — API spec obtained from TNT v2

---

## 1. What Bonfires.ai Is

Bonfires.ai is a knowledge coordination platform built by [DeSciWorld](https://desci.world/). It transforms group conversations (Telegram, Discord) into persistent, queryable knowledge graphs. Each "Bonfire" is an independent knowledge engine comprising:

- **Neo4j** graph (populated via [Graphiti](https://github.com/getzep/graphiti)) — entities, relationships, episodes
- **Weaviate** vector store — semantic embeddings for similarity search
- **MongoDB** document store — raw chunks, summaries, taxonomy labels

Bonfires are currently centralized (team-deployed, Genesis NFT gated). A federated **Knowledge Network** with self-hosted participation and $KNOW token economics is planned but not yet live.

### kEngrams — The Portable Knowledge Unit

The canonical exportable unit is the **kEngram**:

| Field | Description |
|-------|-------------|
| Content | Fact, relationship, insight, or pattern |
| Attribution | Who contributed — individuals, Bonfire collectively, or derived |
| Provenance | Source Bonfire, originating episodes, timestamp |
| Embedding | Vector position in semantic space |
| Metadata | Endorsements, retrieval history, contributor reputation, stakes |

### Gravitational Scoring Model

Bonfires values kEngrams using a formula strikingly similar to our emission model:

```
V = G * (mass_output * mass_target) / f(distance)

where:
  distance     = (1 - semantic_similarity) / semantic_similarity
  mass_output  = info_mass(k) * reputation(author) * stake(Bonfire)
  info_mass(k) = 1 + log(1 + retrieval_count)
```

Compare to our topology score:
```
score = 0.6 * min(betweenness, 1.0)
      + 0.4 * min(log1p(edge_weight_sum) / log1p(50), 1.0)
```

Both systems use semantic proximity and retrieval frequency as value signals. Both apply logarithmic dampening to prevent saturation. The mathematical alignment is strong enough that kEngram mass could map directly to our node attestation scores.

### Two Different Kinds of Graph

These systems are **not the same kind of graph**, and the integration design depends on understanding this distinction clearly.

| Property | Narrative Network (KùzuDB) | Bonfires (Neo4j/Graphiti) |
|----------|---------------------------|--------------------------|
| Node semantics | Attractor basin (centroid embedding + persona + corpus) | Named entity (person, org, concept) |
| Edge semantics | Weighted navigability (float + decay + traversal count) | Typed relationship (string label: "operates", "uses") |
| Graph purpose | Route traversals, compute centrality for emissions | Represent extracted knowledge for retrieval |
| Evolution model | Reinforcement + decay (continuous, ecological) | Append-only extraction (episodic, geological) |
| Aliveness metaphor | **Ecological** — birth, competition, death, decay. Unused paths atrophy. | **Geological** — sedimentation, accretion, preservation. Nothing is forgotten. |

The Narrative Network graph at any moment is a *living organism*. The Bonfires projection of it is a *fossil record* — preserving what the organism forgets. The fossil record is valuable precisely because of this difference.

The projection works **only because it is unidirectional**. If anyone tries to reason over the Bonfires projection as if it were the live graph (compute metrics, derive weights, make scoring decisions), the semantic mismatch will produce misleading results.

---

## 2. Integration Mental Models

### Model A: Bonfires as Seed Crystal

Bonfires provides the **initial graph topology** that the Narrative Network bootstraps from. Before any miner registers, the network needs a starting set of knowledge domains, their relationships, and corpus content. A Bonfire's Neo4j graph of entities and relationships becomes the seed for our KùzuDB node/edge structure.

**Flow:**
```
Bonfire graph (Neo4j)
  → export entities as domain candidates
  → export relationships as initial edge proposals
  → export episodes as seed corpus chunks
  → load_from_dict() into validator KùzuDB instances
```

**When this applies:** Network genesis. One-time or infrequent bootstrap.

**Key principle:** The seed crystal dissolves. Once miners register real domains and validators begin scoring, the emergent topology diverges from the bootstrap. The Bonfire seed is scaffolding, not foundation.

### Model B: Bonfires as Community Memory Layer

The Narrative Network generates attestations, traversal history, and topology evolution. This is valuable signal that communities want to query, visualize, and discuss. Bonfires excels at making knowledge conversationally accessible.

**Flow:**
```
Validators (KùzuDB, per-epoch)
  → snapshot graph state (nodes, edges, traversal events)
  → write episodes to Bonfire via episode write API
  → kEngrams are generated from attestation records
  → community queries graph via Bonfire agents (Telegram, Discord, MCP)
```

**When this applies:** Ongoing, post-launch. The Bonfire becomes the "community dashboard" layer.

**Key principle:** The Bonfire is a read-optimized mirror, not the source of truth. Validators never read from Bonfires for scoring. The data flows one direction: subnet → Bonfire.

### Model C: Bonfires as Discovery Surface

New miners need to identify underserved domains before proposing nodes. A Bonfire that mirrors the current graph state lets prospective miners:

- Browse existing domains and their coverage
- Identify structural gaps (domains with high betweenness potential)
- Understand what personas and corpora are needed
- Draft proposals informed by the live topology

**Flow:**
```
Bonfire (graph mirror)
  → prospective miner browses via Graph Explorer / agent chat
  → identifies opportunity
  → prepares DomainManifest
  → submits proposal to subnet
```

**Key principle:** Discovery is advisory, not authoritative. The Bonfire shows what the graph looks like; the on-chain metagraph is what determines what's real.

---

## 3. What We Do NOT Use Bonfires For

- **Validator scoring source** — Validators maintain KùzuDB locally. They never query Bonfires for edge weights, centrality, or attestation data during scoring epochs.
- **Consensus mechanism** — Each validator independently calls `set_weights()` on Subtensor; Yuma Consensus aggregates. Bonfires has no role in weight setting or consensus.
- **Session state** — Redis owns session state. Bonfires is not on the hot path for traversal requests.
- **Canonical graph of record** — The union of all validator KùzuDB instances + Subtensor weight matrix is the canonical graph. Bonfires is a projection of it.

---

## 4. TNT v2 API Surface

**Base URL:** `https://tnt-v2.api.bonfires.ai`
**Auth:** Bearer token (API key obtained via Genesis NFT provision or agent purchase)
**Docs:** `https://tnt-v2.api.bonfires.ai/docs` (Swagger/OpenAPI)

### 4.1 Write Path — Validator → Bonfires

These are the endpoints we use to push subnet state into Bonfires after each scoring epoch.

#### Knowledge Graph Writes

| Endpoint | Method | Purpose in our integration |
|----------|--------|---------------------------|
| `/knowledge_graph/entity` | POST | Create domain nodes as Bonfires entities |
| `/knowledge_graph/edge` | POST | Create edges between entities (src_uuid, dst_uuid, relation_type) |
| `/knowledge_graph/add_triples` | POST | **Batch** add triples — preferred for epoch sync (one call per epoch) |
| `/knowledge_graph/episode/create` | POST | Create episodes directly via Graphiti — maps to our TraversalEvents |
| `/knowledge_graph/episode_update` | POST | Update existing episodes with new attestation data |

**Primary sync endpoint:** `POST /knowledge_graph/add_triples` for structural updates (nodes + edges as triples), plus `POST /knowledge_graph/episode/create` for traversal events.

Request schemas:

```python
# Create entity (domain node)
# Entity name includes miner UID to prevent identity collision on prune-then-reuse.
# If node "emergent-systems" is pruned and a different miner re-proposes it,
# Graphiti would otherwise merge the new entity with the dead one's history.
POST /knowledge_graph/entity
{
    "bonfire_id": "698b70002849d936f4259848",
    "entity_name": "emergent-systems:uid42",   # node_id:miner_uid — globally unique
    "entity_type": "narrative_domain"
}
# Response: { "uuid": "...", "entity_name": "...", "entity_type": "..." }

# Create edge — ALWAYS use fixed relation type, never encode weights in type string
POST /knowledge_graph/edge
{
    "bonfire_id": "698b70002849d936f4259848",
    "source_uuid": "<entity_uuid_1>",
    "target_uuid": "<entity_uuid_2>",
    "relation_type": "TRAVERSAL_LINK"
}

# Batch add triples (preferred for epoch sync)
# Use fixed relation type. Weight data goes in episode metadata, not here.
POST /knowledge_graph/add_triples
{
    "bonfire_id": "698b70002849d936f4259848",
    "triplets": [
        {
            "entity_from": "emergent-systems",
            "relation": "TRAVERSAL_LINK",
            "entity_to": "complexity-theory"
        },
        ...
    ]
}

# Edge weights are pushed as a companion epoch-state episode (not in triple relations)
# This avoids Neo4j schema pollution — encoding weights in relation type strings
# (e.g., "LINKS_TO:0.85") creates a new relationship type per weight value per sync.
POST /knowledge_graph/episode/create
{
    "bonfire_id": "698b70002849d936f4259848",
    "agent_id": "<our_sync_agent_id>",
    "content": {
        "type": "epoch_edge_state",
        "epoch": 42,
        "edges": [
            {
                "src": "emergent-systems",
                "dst": "complexity-theory",
                "weight": 0.85,
                "traversal_count": 17,
                "last_traversed": 1710547200.0
            }
        ]
    }
}

# Create episode (traversal event)
POST /knowledge_graph/episode/create
{
    "bonfire_id": "698b70002849d936f4259848",
    "agent_id": "<our_sync_agent_id>",
    "content": {
        "session_id": "sess_abc123",
        "epoch": 42,
        "path": ["node_a", "node_b", "node_c"],
        "attestation_scores": {
            "miner_uid_7": { "groundedness": 0.82, "coherence": 0.91, "edge_utility": 0.74 }
        },
        "passage_text": "The winning passage...",
        "passage_embedding": [0.1, 0.2, ...]
    }
}
```

#### Content Ingestion (for corpus sync)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ingest_content` | POST | Push miner corpus chunks for community browsing |
| `/ingest_content_vector_only` | POST | Lighter path — vectorize without summarization |
| `/ingest_pdf` | POST | Upload PDF corpora directly |

#### Agent Stack (for real-time event streaming)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/agents/{agent_id}/stack/add` | POST | Push messages (epoch summaries, lifecycle events) to agent's episodic stack |
| `/agents/{agent_id}/stack/process` | POST | Trigger background processing of stacked messages |

The agent stack is the most natural fit for **streaming epoch events** — each epoch summary becomes a message on the stack, processed into the knowledge graph asynchronously by Bonfires' own pipeline.

### 4.2 Read Path — Bonfires → Bootstrap

These endpoints support pulling graph state for validator bootstrap and miner discovery.

#### Graph Queries

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/delve` | POST | Unified semantic search across the graph — primary discovery endpoint |
| `/knowledge_graph/entity/{uuid}` | GET | Fetch single entity by UUID |
| `/knowledge_graph/entities/batch` | POST | Batch fetch entities — for bulk bootstrap |
| `/knowledge_graph/expand/entity` | POST | Expand entity to reveal connected edges and nodes |
| `/knowledge_graph/episodes/expand` | POST | Expand episodes with connected graph structure |
| `/knowledge_graph/node/{node_uuid}/episodes` | GET | Get all episodes mentioning a node (limit 200) |
| `/knowledge_graph/agents/{agent_id}/episodes/latest` | GET | Latest episodes with hydrated nodes and edges |

```python
# Delve search (discovery)
POST /delve
{
    "bonfire_id": "698b70002849d936f4259848",
    "query": "knowledge domains related to complexity theory"
}

# Expand entity (bootstrap — get a node and all its connections)
POST /knowledge_graph/expand/entity
{
    "bonfire_id": "698b70002849d936f4259848",
    "entity_uuid": "<uuid>"
}
# Response: { "nodes": [...], "edges": [...] }
```

#### Vector Search

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/vector_store/search` | POST | Semantic search over chunks — for finding related domains |
| `/vector_store/chunks/{bonfire_id}` | GET | Get labeled chunks for a bonfire |

### 4.3 Agent Infrastructure

We register a **sync agent** on our Bonfire — a dedicated agent identity that the validator uses to push data. Community users interact with the Bonfire's chat agents; the sync agent is write-only infrastructure.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/agents` | POST | Create our sync agent |
| `/agents/register` | POST | Register sync agent to our Bonfire |
| `/agents/{agent_id}/chat` | POST | Not used by us — community-facing |
| `/agents/{agent_id}/chat/stream` | POST | Not used by us — community-facing |

### 4.4 Attestations

Bonfires has a native attestation system — episodes can have attestation UIDs attached:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/knowledge_graph/agents/{agent_id}/attestations` | GET | Retrieve attestation UIDs for agent episodes |

This could map to our validator attestation records. Worth exploring whether Bonfires attestations can reference EAS (Ethereum Attestation Service) UIDs from Alkahest integration.

---

## 5. Sync Bridge Design

### 5.1 Validator → Bonfires Sync

Each validator exports graph state to Bonfires after scoring epochs. The sync is **unidirectional** (validator → Bonfires) and **eventually consistent** (lag is acceptable).

```
Validator (post-epoch)
  │
  ├─ 1. Serialize graph delta since last sync:
  │     - New/updated nodes (node_id, domain, centroid, state)
  │     - Edge weight changes (src, dst, new_weight, traversal_count)
  │     - Traversal events (session_id, path, attestation_scores)
  │     - Node lifecycle transitions (incubating → live, live → warning, etc.)
  │
  ├─ 2. Choose write strategy:
  │     a. Structural changes (nodes + edges):
  │        → POST /knowledge_graph/add_triples  (batch, one call per epoch)
  │     b. Traversal events:
  │        → POST /knowledge_graph/episode/create  (one per significant session)
  │     c. Epoch summary narrative:
  │        → POST /agents/{sync_agent_id}/stack/add  (streamed to agent stack)
  │
  ├─ 3. Write is async, non-blocking, fire-and-forget with retry
  │     - Failure never blocks validator scoring
  │     - Retry with exponential backoff (max 3 attempts)
  │     - Log failures for manual reconciliation
  │
  └─ 4. Confirm write (Bonfires returns episode UUID / triple count)
```

**Conflict resolution:** Multiple validators may sync overlapping data. Bonfires' Graphiti layer handles deduplication — new extractions are matched against existing entities/relationships and merged rather than duplicated. This is a native Graphiti feature, not something we need to build.

### 5.2 Bonfires → Validator Bootstrap

At network genesis or when a new validator joins:

```
New validator
  │
  ├─ 1. Fetch bootstrap snapshot from Bonfires:
  │     a. POST /knowledge_graph/entities/batch  (all domain entities)
  │     b. POST /knowledge_graph/expand/entity   (per entity, get edges)
  │     c. GET  /knowledge_graph/node/{uuid}/episodes  (recent traversals)
  │
  ├─ 2. Transform from Bonfires format to GraphStore dict:
  │     {
  │       "nodes": [{ "node_id": "emergent-systems", "domain": "...", ... }],
  │       "edges": [{ "src": "emergent-systems", "dst": "complexity-theory", "weight": 1.0, ... }]
  │     }
  │     NOTE: All edge weights set to uniform default (1.0).
  │     Bootstrap provides topology shape only, not state.
  │     Entity name UID suffix stripped for node_id (e.g., "emergent-systems:uid42" → "emergent-systems").
  │
  ├─ 3. Load via graph_store.load_from_dict(data)
  │
  └─ 4. Verify against on-chain metagraph (UIDs, registered nodes)
      - Any discrepancy → trust the chain
      - Begin normal epoch scoring
      - Graph diverges from Bonfires state immediately
```

**Trust boundary — CRITICAL:** The bootstrap snapshot is advisory, not authoritative. Bonfires is a centralized, trusted platform — a compromised or manipulated Bonfires instance could feed a new validator a poisoned initial graph with manipulated edge weights and centrality scores that still looks consistent with on-chain UIDs.

New validators MUST:
1. Verify the Bonfires snapshot against the on-chain metagraph (UIDs, registered nodes). Any discrepancy → trust the chain.
2. **Use bootstrap only for topology shape** — which nodes exist and roughly how they connect. This is safe because topology is verifiable against on-chain UID registrations.
3. **Never use bootstrapped edge weights for emission calculations.** Set all bootstrapped edge weights to a uniform default (e.g., `1.0`) and re-derive weights from local scoring within the first N epochs.
4. **Re-derive betweenness centrality locally** after the first scoring epoch rather than trusting bootstrapped centrality values.

The bootstrap accelerates discovery of graph structure. It does NOT accelerate trust in graph state.

### 5.3 Sync Frequency

| Event | Sync action | API call | Latency tolerance |
|-------|------------|----------|-------------------|
| Epoch completion | Push graph delta | `add_triples` + `episode/create` | Minutes (async) |
| Node lifecycle transition | Push state change | `entity` update | Minutes |
| New validator bootstrap | Pull full snapshot | `entities/batch` + `expand/entity` | One-time, can be slow |
| Corpus update | Push miner content | `ingest_content` | Hours (background) |
| Graph visualization | Bonfires reads own Neo4j | N/A (internal) | Real-time |

---

## 6. Data Format Translation

### KùzuDB → Bonfires Entity Mapping

| KùzuDB (our schema) | Bonfires (Neo4j/Graphiti) | Notes |
|---------------------|--------------------------|-------|
| `Node` | Entity node | `node_id:uid` → entity name (UID suffix prevents prune-reuse collision), `domain` → entity type |
| `Edge` | `TRAVERSAL_LINK` relationship + epoch-state episode | Relationship captures topology; episode captures weight/traversal/decay state |
| `TraversalEvent` | Episode | `session_id` → episode ID, `path` → episode content |
| Attestation scores | Episode metadata | Per-miner scores embedded in episode content |
| Betweenness centrality | Entity metadata | Computed metric stored as entity property; label with epoch timestamp for staleness |
| Node state (incubating/live/warning/pruning) | Entity label | Maps to Bonfires taxonomy |

### Node Identity: Prune-then-Reuse Collision

Graphiti deduplicates entities by name on ingest. If a node is pruned from the subnet and a different miner later re-proposes the same `node_id`, Graphiti would merge the new entity with the dead one's history — inheriting wrong provenance.

**Mitigation:** Entity names include the miner UID suffix (`emergent-systems:uid42`). Different miners registering the same domain concept create distinct Bonfires entities. When a node is pruned, the sync agent pushes a lifecycle episode marking it as pruned (no entity deletion needed — the fossil record is valuable).

### Edge Weights: Topology vs. State

Bonfires edges are typed relationships (categorical strings). Our edges carry continuous-valued state (weight, traversal count, decay). These are fundamentally different representations.

**Resolution:** Split the sync into two layers:
1. **Topology** (`TRAVERSAL_LINK` relationships via `add_triples`) — captures *which* nodes connect. Fixed relation type, no weight encoding. Graphiti dedup handles this cleanly.
2. **State** (epoch-state episodes via `episode/create`) — captures *how strong* connections are at a point in time. JSON content with edge weights, traversal counts, centrality scores, timestamps.

This separation means the Bonfires graph structure reflects topology (which is relatively stable), while episodes capture the time-varying dynamics (which change every epoch). Community tools query episodes for current state; the graph structure shows navigability.

### kEngram ↔ Attestation Record

A kEngram maps naturally to a **validated traversal hop**:

| kEngram field | Narrative Network equivalent |
|--------------|------------------------------|
| Content | Winning passage text + knowledge synthesis |
| Attribution | Winning miner UID + validator UIDs who scored it |
| Provenance | Session ID, epoch number, source/destination nodes |
| Embedding | Passage embedding (from NarrativeHop response) |
| Metadata | Groundedness/Coherence/Edge Utility scores, traversal count |

This mapping means every scored hop in the Narrative Network can be expressed as a kEngram and written to Bonfires. Over time, the Bonfire accumulates the network's entire attestation history as queryable knowledge.

---

## 7. Implementation Phases

### Phase 0 — Provision Bonfire + Sync Agent (now)

- Mint Genesis NFT (0.1 ETH) at `https://mint.bonfires.ai` to get a hosted Bonfire
- `POST /provision` with tx_hash to create off-chain resources → receive `bonfire_id` + API key
- `POST /agents` to create a sync agent (e.g., `narrative-network-sync`)
- `POST /agents/register` to bind sync agent to our Bonfire
- Test write path: `POST /knowledge_graph/add_triples` with sample domain data
- Test read path: `POST /delve` to verify entities are queryable

### Phase 1 — Bootstrap Seed (MVP)

- If seeding from an existing Bonfire:
  - `POST /knowledge_graph/entities/batch` to fetch existing entities
  - `POST /knowledge_graph/expand/entity` per entity to get edges
  - Transform to `load_from_dict` format
- If seeding fresh:
  - Create initial domain entities via `POST /knowledge_graph/entity`
  - Create initial edges via `POST /knowledge_graph/edge`
  - Push seed corpus via `POST /ingest_content`
- Load into validator KùzuDB instances
- Verify against on-chain metagraph

### Phase 2 — Epoch Sync (Finney testnet)

- Implement `BonfiresSyncAdapter` in validator:
  ```python
  class BonfiresSyncAdapter:
      """Async, non-blocking sync bridge. Failure never blocks scoring."""

      BASE_URL = "https://tnt-v2.api.bonfires.ai"

      def __init__(self, bonfire_id: str, api_key: str, sync_agent_id: str):
          self.bonfire_id = bonfire_id
          self.api_key = api_key
          self.sync_agent_id = sync_agent_id

      async def push_epoch_delta(self, delta: GraphDelta) -> dict:
          """Push structural changes as triples + traversal events as episodes."""
          # 1. Structural: POST /knowledge_graph/add_triples
          # 2. Traversals: POST /knowledge_graph/episode/create (per session)
          # 3. Summary: POST /agents/{sync_agent_id}/stack/add
          ...

      async def pull_bootstrap_snapshot(self) -> dict:
          """Pull full graph for load_from_dict(). One-time use."""
          # 1. POST /knowledge_graph/entities/batch
          # 2. POST /knowledge_graph/expand/entity (per entity)
          # 3. Transform to { "nodes": [...], "edges": [...] }
          ...

      async def push_content(self, corpus_chunks: list[dict]) -> str:
          """Push miner corpus for community browsing."""
          # POST /ingest_content or /ingest_content_vector_only
          ...
  ```
- Validator calls `push_epoch_delta` after each scoring epoch
- Async, non-blocking, failure-tolerant (retry with backoff, max 3 attempts)
- Log sync status to Prometheus: `bonfires_sync_success_total`, `bonfires_sync_failure_total`, `bonfires_sync_latency_seconds`

### Phase 3 — Community Layer (Mainnet)

- Bonfire agents (Telegram, Discord) can answer questions about graph state
- Graph Explorer at `graph.bonfires.ai` shows live topology
- Prospective miners browse via Bonfire to identify opportunities
- kEngrams accumulate as the network's public attestation record
- Explore DataRooms (`POST /datarooms`) for gated access to premium graph segments
- Explore HyperBlogs for AI-generated articles from graph knowledge (monetized via x402)

### Phase 4 — Knowledge Network Integration (post-$KNOW TGE)

- Self-hosted Bonfire option eliminates Genesis NFT dependency
- Cross-Bonfire knowledge sharing via Knowledge Network
- kEngram retrieval tracking feeds back into $KNOW economics
- Explore TAO ↔ $KNOW cross-chain bridge for unified incentives

---

## 8. Open Questions for Bonfires Team

1. **Rate limits** — What are the rate limits on `add_triples` and `episode/create`? We'll push ~1 batch per epoch (every few minutes).
2. **Bulk export** — Can we get a full graph snapshot (all entities + edges) in a single call? Current approach requires N+1 calls (batch entities + expand each).
3. **Self-hosted timeline** — When does the Knowledge Network support self-hosted Bonfires?
4. **Entity deduplication strategy** — Graphiti deduplicates on ingest. Is matching by name-exact, embedding-similarity, or configurable? We use `node_id:uid` entity names to prevent prune-reuse collision — will Graphiti treat `emergent-systems:uid42` and `emergent-systems:uid99` as distinct entities?
5. **Attestation UID format** — Can attestation UIDs reference EAS attestations from Alkahest? What's the expected format?
6. **$KNOW ↔ TAO** — As Knowledge Network launches, is cross-chain bridge planned?
7. **Webhook/events** — Does Bonfires support outbound webhooks when entities/episodes are created?
8. **Episode query by type** — Can we filter episodes by content type (e.g., `type: "epoch_edge_state"` vs `type: "traversal_event"`)? This affects how community tools retrieve current-state snapshots vs historical traversals.

---

## 9. Confluence and Divergence Analysis

### Where the Systems Align Naturally

| Dimension | Alignment | Integration value |
|-----------|-----------|-------------------|
| **Scoring math** | Both use `log1p` dampening, retrieval frequency, semantic proximity | Attestation scores as kEngram metadata enriches Bonfires with a quality dimension it lacks natively |
| **Episode ↔ TraversalEvent** | Both are timestamped event records with structured content | Direct mapping via `episode/create`; use distinct sync agent to separate machine data from organic conversation |
| **Multi-validator dedup** | Graphiti merges duplicate entities by name | Solves the N-validators-pushing-same-data problem for free |
| **Complementary value signals** | Attestation = "how well served" (relative); Gravitational mass = "how much it matters" (absolute) | Orthogonal signals that compose rather than compete |

### Where the Systems Diverge

| Dimension | Tension | Resolution |
|-----------|---------|------------|
| **Edge semantics** | Continuous float weights vs. categorical typed strings | Split into topology (relationships) + state (episodes). Permanent gap — accept it. |
| **Temporal dynamics** | Decay/reinforcement vs. append-only persistence | Bonfires accumulates a time-smeared view. Label all data with epoch timestamps; consumer tools must filter by recency. |
| **Node identity** | Attractor basins (embedding-defined) vs. named entities (string-defined) | Lossy projection. UID-suffixed names prevent collision. Do not build systems that round-trip entity identity. |
| **Trust model** | Trustless (independent validators + Subtensor) vs. trusted (centralized platform) | Unidirectional flow. Bootstrap uses topology only, not weights. Validators re-derive all state locally. |
| **Graph "aliveness"** | Ecological (things die) vs. geological (nothing forgotten) | Complementary, not conflicting. The fossil record preserves what the organism forgets. |

---

## 10. Risk Assessment

| Risk | Severity | Mitigation | Status |
|------|----------|------------|--------|
| Rate limits unknown | Medium | Test in Phase 0; batch-friendly sync (one call per epoch) | Open |
| Bonfires centralized — SPOF | Medium | Sync is optional, non-blocking; scoring never depends on Bonfires | Accepted |
| No bulk export endpoint | Medium | Iterative bootstrap (entities/batch + expand); request bulk export | Open |
| Bootstrap trust gap | Medium | Bootstrap topology only; uniform default weights; re-derive locally within N epochs | **Mitigated** |
| Edge weight schema pollution | High → Fixed | Use fixed `TRAVERSAL_LINK` relation type; weights in epoch-state episodes | **Fixed** |
| Prune-then-reuse identity collision | Medium → Fixed | UID-suffixed entity names (`node_id:uid`); lifecycle episodes on prune | **Fixed** |
| Graphiti dedup may not match semantics | Medium | Test UID-suffixed names in Phase 0; confirm distinct treatment | Open |
| Temporal smearing (no decay in Bonfires) | Low | Label all data with epoch timestamps; document for consumer tools | Accepted |
| Knowledge Network not yet live | Low | Phase 1-3 with hosted Bonfire; self-hosted is Phase 4 | Accepted |

---

*Bonfires is the campfire where the network's stories are retold. Validators write the canonical history in KùzuDB and on-chain. Bonfires makes that history conversationally accessible — a community memory layer, not a consensus layer.*
