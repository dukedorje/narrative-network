# Hole Detection & Probing

How the Coherence Engine finds what's missing in the knowledge graph.

---

## Knowledge Graph Holes

A **hole** is a gap in the knowledge graph — not a wrong node, but a *missing* one. The graph's topology implies connections that don't exist yet, concepts that should be bridged but aren't, regions of embedding space that are suspiciously empty.

Holes are the complement of counterfactuals. Counterfactuals are things that are present but shouldn't be. Holes are things that are absent but should be.

### Types of Holes

| Hole Type | How to Detect | Example |
|-----------|--------------|---------|
| **Topological hole** | Islands or near-islands in the graph — clusters with no or very few bridge paths between them | Two well-developed domains (quantum mechanics, philosophy of mind) with no nodes connecting them, despite conceptual overlap |
| **Embedding void** | Regions of embedding space where existing nodes' centroids imply coverage but no node exists | Three nodes surround a region in embedding space — their edges "point through" the void but nothing is there |
| **Narrative dead end** | Nodes with high inbound traffic but no compelling outbound paths — traversals terminate prematurely | A popular node that players always leave via the same single edge, because there's nowhere else interesting to go |
| **Asymmetric bridge** | Two nodes connected in one direction but not the other — the relationship is incomplete | "Quantum mechanics → computation" exists but "computation → quantum mechanics" has no narrative path |
| **Stale frontier** | Edges of the graph where the last integration happened long ago and the surrounding knowledge landscape has evolved | A domain that was cutting-edge when added but the real world has moved on — the graph's frontier is outdated |

### Detection Methods

**Topological analysis:**
- Compute connected components and near-components (clusters connected by only 1-2 edges)
- Identify nodes with high betweenness centrality that are load-bearing — if they were removed, what disconnects?
- Find long shortest-paths between conceptually related nodes (high embedding similarity but high graph distance)

**Embedding space analysis:**
- Voronoi decomposition of node centroids in embedding space — large empty cells suggest missing domains
- Convex hull of the graph's embedding coverage — what's inside the hull but unoccupied?
- Density estimation — regions where the graph "should" have nodes based on the distribution of existing ones

**Traversal pattern analysis:**
- Dead-end detection: nodes where sessions disproportionately terminate
- Bounce detection: nodes where traversals arrive and immediately leave (high traffic, low dwell)
- Path frustration: sessions that loop or backtrack, suggesting the graph lacks forward paths

**Cross-reference with external knowledge:**
- Generalized into the probing system (see below)

---

## Probing

**Probing** is the generalized version of what unbrowse currently does at specific moments. A probe is an agent action that reaches outside the current knowledge graph to check for missing knowledge, validate existing knowledge, or discover new connections.

### Current Integration Points (as Probes)

| Current Integration Point | Generalized Probe Type |
|--------------------------|----------------------|
| Corpus fallback (domain_similarity < threshold) | **Deficit probe** — the graph can't answer a query, go find what's missing |
| Foreshadowing enrichment | **Frontier probe** — enrich a newly integrating node with external context |
| Proposal domain validation | **Validation probe** — verify that a proposed domain has real-world substance |
| Gateway query grounding | **Entry probe** — the query doesn't match any node well, find where it should land |

### Additional Probe Types

| Probe Type | Trigger | Purpose |
|-----------|---------|---------|
| **Void probe** | Embedding space analysis finds an empty region | Investigate whether knowledge exists that should fill this hole |
| **Bridge probe** | Topological analysis finds disconnected clusters | Search for concepts that could connect two islands |
| **Staleness probe** | Stale frontier detection flags an outdated region | Check if the real world has moved on from this domain's current representation |
| **Contradiction probe** | Two nodes make claims that may conflict | Seek external evidence to resolve or contextualize the disagreement |
| **Depth probe** | A node has high traffic but shallow corpus | The graph knows *about* something but not enough — go deeper |

### Probe Abstraction

A probe is a first-class abstraction with a common interface:

```
Probe:
  trigger:     What condition initiated this probe
  query:       What to search for
  scope:       Which part of the graph this relates to
  budget:      How much compute/cost to spend
  source:      Where to look (unbrowse, other APIs, other subnets, other lenses)
  callback:    What to do with results (integrate, flag, propose, enrich)
```

Unbrowse becomes one *source* among potentially many. Other sources could include: other subnets on Bittensor, other lenses within the same network, domain-specific APIs, academic databases, etc.

---

## Across Lenses

| Aspect | Knowledge Network | Game | Composable Network |
|--------|-------------------|------|-------------------|
| Primary hole type | Embedding voids, stale frontiers | Narrative dead ends, unexplored territory | Topological holes at composition boundaries |
| Probe style | Research queries, citation searches | Not primary — world generates from within | Cross-subgraph queries, membrane probes |
| Scheduling priority | Hole detection > probing > integration | Bridge-building > counterfactuals > probing | Composition maintenance > hole detection > probing |

---

## Relationship to Other Physics

- **Counterfactual Detection**: Pruning can *create* holes — removing a node may disconnect part of the graph. Hole detection should run after significant pruning. See [counterfactual-detection.md](counterfactual-detection.md).
- **World Model**: The world model implies what *should* exist — holes are gaps between what the axioms predict and what the graph contains. See [world-model.md](world-model.md).
- **Internal Economics**: Probing costs energy. The probe budget is part of each agent's energy allocation. See [internal-economics.md](internal-economics.md).
- **Observation & Integration**: Probe results feed into the integration pipeline — discovered knowledge still needs to go through FORESHADOW → BRIDGE → LIVE. See [observation-and-integration.md](observation-and-integration.md).

---

## Relationship to Existing Systems

- **Unbrowse** → becomes one probe source among many, behind the Probe abstraction
- **Pruning** → already detects one kind of hole-adjacent problem (underperforming nodes), but doesn't detect *missing* nodes
- **Edge decay** → edges decaying to floor can reveal emergent holes (formerly-connected regions becoming disconnected)
