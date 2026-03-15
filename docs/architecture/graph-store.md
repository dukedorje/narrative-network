# Graph Store

## Overview

`GraphStore` is the knowledge graph storage layer used by both miners and validators. It maintains a graph of narrative nodes and weighted edges, supports traversal logging, and exposes topology metrics used in validator scoring.

---

## Architecture

`GraphStore` composes two layers:

- `_MemoryGraph` — always present; holds all nodes, edges, and traversal logs in memory for fast access
- `KùzuDB` — optional persistent backend; when configured, all structural mutations are mirrored to disk

Thread safety is enforced by a single write lock. Read-heavy paths use copy-on-read for critical sections to avoid holding the lock during iteration.

---

## Data Model

### Node

```
node_id     : str      — globally unique identifier
domain      : str      — thematic domain of the node
persona     : str      — narrative voice or character
uid         : int      — Bittensor UID of the owning miner
created_at  : float    — Unix timestamp
```

### Edge

```
src              : str    — source node_id
dst              : str    — destination node_id
weight           : float  — current edge weight
traversal_count  : int    — number of times this edge has been traversed
last_traversed   : float  — Unix timestamp of most recent traversal
created_at       : float  — Unix timestamp
```

### TraversalLog

```
session_id     : str    — unique session identifier
path           : list   — ordered sequence of node_ids
quality_score  : float  — score assigned to this traversal
timestamp      : float  — Unix timestamp
```

---

## Operations

### Node Operations

| Method | Description |
|---|---|
| `add_node(node)` | Insert a node; no-op if `node_id` already exists |
| `get_node(node_id)` | Return the `Node` dataclass or `None` |
| `all_node_ids()` | Return a list of all node identifiers |
| `uid_to_node(uid)` | Return the `node_id` mapped to a given miner UID |

### Edge Operations

| Method | Description |
|---|---|
| `add_edge(edge)` | Insert edge; if it already exists, keeps the maximum weight of the two |
| `update_weight(src, dst, delta)` | Add `delta` to edge weight; floored at 0 |
| `record_traversal(src, dst)` | Increment `traversal_count`, update `last_traversed`, boost weight by 5% capped at 10.0 |

### Decay

`decay_all(rate)` multiplies every edge weight by `(1 - rate)`. Edges that fall below `0.01` are pruned from the graph. This is called by validators after each weight commit to age stale connections.

### Traversal Logging

`log_traversal(session_id, path, quality_score)` records a `TraversalLog` entry and calls `record_traversal` for each consecutive node pair in the path.

---

## Query Methods

### `neighbours(node_id, top_k)`

Returns the `top_k` outgoing neighbours of `node_id`, sorted by descending edge weight.

### `bfs_path(start, end)`

Returns the shortest path between `start` and `end` using breadth-first search. Returns `None` if no path exists.

### `sample_edges(n)`

Returns `n` randomly sampled edges. Used by validators when constructing corpus challenges.

---

## Betweenness Centrality

Betweenness centrality is computed using Brandes' algorithm (O(VE)), which is suitable for graphs up to approximately 500 nodes.

The result is normalised for directed graphs:

```
normalised_betweenness = raw / ((n - 1) * (n - 2))
```

The computed values are cached. A staleness flag is set on any structural mutation — `add_node`, `add_edge`, `record_traversal`, or `decay_all` — and the cache is recomputed on the next topology query.

---

## Topology Score

The topology score for a node is:

```
score = 0.6 * min(betweenness, 1.0)
      + 0.4 * min(log1p(edge_weight_sum) / log1p(50), 1.0)
```

- Betweenness (60%): rewards nodes that lie on many shortest paths, indicating bridge position between clusters. A node can score high here even with low raw traffic.
- Edge weight sum (40%): soft-capped via `log1p` with a reference ceiling of 50, preventing a small number of very heavy edges from saturating the score.

---

## KùzuDB Schema

When KùzuDB persistence is enabled, the following schema is used:

**Node table**

```sql
CREATE NODE TABLE Node (
    id          STRING,
    domain      STRING,
    persona     STRING,
    uid         INT64,
    created_at  DOUBLE,
    PRIMARY KEY (id)
)
```

**Edge relationship table**

```sql
CREATE REL TABLE Edge (
    FROM Node TO Node,
    weight           DOUBLE,
    traversal_count  INT64,
    last_traversed   DOUBLE
)
```

Upserts use `MERGE` semantics so re-inserting an existing node or edge updates rather than duplicates the record.

---

## Bulk Load

`load_from_dict(data)` accepts a dictionary with two keys:

```python
{
    "nodes": [ { "node_id": ..., "domain": ..., "persona": ..., "uid": ..., "created_at": ... }, ... ],
    "edges": [ { "src": ..., "dst": ..., "weight": ..., ... }, ... ]
}
```

This is used during bootstrap to populate the graph from a serialised snapshot without going through the individual `add_node` / `add_edge` paths.
