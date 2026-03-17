"""Graph store for the living knowledge graph.

_MemoryGraph provides thread-safe in-process storage with adjacency lists.
GraphStore wraps _MemoryGraph and always persists to KuzuDB (temp dir when no path given).

# FUTURE: Bonfires DB sync -- push graph state to centralized Bonfires
# TNT v2 API. Different validators intentionally maintain divergent graphs.
# Sync to Bonfires is the eventual consistency mechanism.
"""

from __future__ import annotations

import collections
import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field

from subnet.config import EDGE_DECAY_FLOOR, EDGE_DECAY_RATE

logger = logging.getLogger(__name__)

try:
    import kuzu  # type: ignore

    _KUZU_AVAILABLE = True
except ImportError:
    _KUZU_AVAILABLE = False
    logger.warning(
        "kuzu not installed — GraphStore will run in memory-only mode. "
        "Install with: pip install kuzu"
    )


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Node:
    node_id: str
    state: str = "Live"          # Live | Incubating | Pruned
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


@dataclass
class Edge:
    source_id: str
    dest_id: str
    weight: float = 1.0
    traversal_count: int = 0
    last_traversal: float = field(default_factory=time.time)


@dataclass
class TraversalLog:
    session_id: str
    source_id: str
    dest_id: str
    passage_embedding: list[float]
    scores: dict[int, float]
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# In-memory graph (thread-safe)
# ---------------------------------------------------------------------------

class _MemoryGraph:
    """Thread-safe in-process graph backed by adjacency dicts."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._nodes: dict[str, Node] = {}
        # _adj[source][dest] = Edge
        self._adj: dict[str, dict[str, Edge]] = collections.defaultdict(dict)
        self._traversal_logs: list[TraversalLog] = []

    # --- Nodes ---

    def add_node(self, node_id: str, state: str = "Live", metadata: dict | None = None) -> Node:
        with self._lock:
            if node_id not in self._nodes:
                self._nodes[node_id] = Node(
                    node_id=node_id, state=state, metadata=metadata or {}
                )
            return self._nodes[node_id]

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def get_live_node_ids(self) -> list[str]:
        with self._lock:
            return [n.node_id for n in self._nodes.values() if n.state == "Live"]

    def get_connected_node_ids(self) -> list[str]:
        """Return IDs of all nodes that have at least one outgoing edge."""
        with self._lock:
            return list(self._adj.keys())

    # --- Edges ---

    def upsert_edge(self, source_id: str, dest_id: str, weight: float = 1.0) -> Edge:
        with self._lock:
            self.add_node(source_id)
            self.add_node(dest_id)
            if dest_id not in self._adj[source_id]:
                self._adj[source_id][dest_id] = Edge(source_id=source_id, dest_id=dest_id, weight=weight)
            return self._adj[source_id][dest_id]

    def reinforce_edge(self, source_id: str, dest_id: str, quality_score: float) -> None:
        with self._lock:
            edge = self.upsert_edge(source_id, dest_id)
            edge.weight = min(edge.weight + quality_score, float(EDGE_DECAY_FLOOR) * 1000)
            edge.traversal_count += 1
            edge.last_traversal = time.time()

    def decay_all(self, decay_rate: float = EDGE_DECAY_RATE) -> int:
        """Apply multiplicative decay to all edges. Returns count of pruned edges."""
        pruned = 0
        with self._lock:
            for src, dests in self._adj.items():
                to_remove = []
                for dest, edge in dests.items():
                    edge.weight = max(edge.weight * decay_rate, EDGE_DECAY_FLOOR)
                    if edge.weight <= EDGE_DECAY_FLOOR:
                        to_remove.append(dest)
                for dest in to_remove:
                    del dests[dest]
                    pruned += 1
        return pruned

    def neighbours(self, node_id: str) -> list[str]:
        return list(self._adj.get(node_id, {}).keys())

    def outgoing_edge_weight_sum(self, node_id: str) -> float:
        with self._lock:
            return sum(e.weight for e in self._adj.get(node_id, {}).values())

    # --- Traversal logs ---

    def record_traversal(self, log: TraversalLog) -> None:
        with self._lock:
            self._traversal_logs.append(log)

    def sample_recent_sessions(self, n: int = 10) -> list[dict]:
        with self._lock:
            recent = sorted(self._traversal_logs, key=lambda l: l.timestamp, reverse=True)[:n]
            return [
                {
                    "session_id": l.session_id,
                    "source_id": l.source_id,
                    "dest_id": l.dest_id,
                    "scores": l.scores,
                    "timestamp": l.timestamp,
                }
                for l in recent
            ]

    # --- Graph algorithms ---

    def brandes_betweenness(self) -> dict[str, float]:
        """Compute unweighted betweenness centrality via Brandes algorithm.

        Returns a dict mapping node_id -> centrality in [0, 1].
        """
        with self._lock:
            nodes = list(self._nodes.keys())

        n = len(nodes)
        if n < 2:
            return {v: 0.0 for v in nodes}

        cb: dict[str, float] = {v: 0.0 for v in nodes}

        for s in nodes:
            # BFS
            stack: list[str] = []
            pred: dict[str, list[str]] = {v: [] for v in nodes}
            sigma: dict[str, float] = {v: 0.0 for v in nodes}
            sigma[s] = 1.0
            dist: dict[str, int] = {v: -1 for v in nodes}
            dist[s] = 0
            queue: collections.deque[str] = collections.deque([s])

            while queue:
                v = queue.popleft()
                stack.append(v)
                for w in self.neighbours(v):
                    if w not in dist:
                        continue
                    if dist[w] < 0:
                        dist[w] = dist[v] + 1
                        queue.append(w)
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        pred[w].append(v)

            delta: dict[str, float] = {v: 0.0 for v in nodes}
            while stack:
                w = stack.pop()
                for v in pred[w]:
                    if sigma[w] > 0:
                        delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
                if w != s:
                    cb[w] += delta[w]

        # Normalise
        if n > 2:
            norm = 1.0 / ((n - 1) * (n - 2))
            cb = {v: cb[v] * norm for v in cb}

        return cb

    def bfs_path(self, source_id: str, dest_id: str) -> list[str] | None:
        """Return shortest path from source to dest via BFS, or None."""
        if source_id == dest_id:
            return [source_id]
        visited = {source_id}
        queue: collections.deque[list[str]] = collections.deque([[source_id]])
        while queue:
            path = queue.popleft()
            node = path[-1]
            for nb in self.neighbours(node):
                if nb == dest_id:
                    return path + [nb]
                if nb not in visited:
                    visited.add(nb)
                    queue.append(path + [nb])
        return None

    # --- Bulk load ---

    def bulk_load(self, nodes: list[dict], edges: list[dict]) -> None:
        """Bulk-insert nodes and edges. Each dict must have 'node_id' / 'source_id'+'dest_id'."""
        with self._lock:
            for n_dict in nodes:
                nid = n_dict["node_id"]
                self._nodes[nid] = Node(
                    node_id=nid,
                    state=n_dict.get("state", "Live"),
                    metadata=n_dict.get("metadata", {}),
                )
            for e_dict in edges:
                src = e_dict["source_id"]
                dst = e_dict["dest_id"]
                self.add_node(src)
                self.add_node(dst)
                self._adj[src][dst] = Edge(
                    source_id=src,
                    dest_id=dst,
                    weight=e_dict.get("weight", 1.0),
                    traversal_count=e_dict.get("traversal_count", 0),
                )

    def stats(self) -> dict:
        with self._lock:
            return {
                "node_count": len(self._nodes),
                "edge_count": sum(len(v) for v in self._adj.values()),
                "live_nodes": sum(1 for n in self._nodes.values() if n.state == "Live"),
                "traversal_log_count": len(self._traversal_logs),
            }


# ---------------------------------------------------------------------------
# Public GraphStore
# ---------------------------------------------------------------------------

class GraphStore:
    """Graph store with in-memory core and KuzuDB persistence.

    KuzuDB is always enabled. When db_path=None, a temporary directory is used.
    If kuzu is not installed, all write operations degrade to memory-only mode.

    Args:
        db_path: Path for KuzuDB persistence. Pass None to use a temp directory.
    """

    def __init__(self, db_path: str | None = "./graph.db") -> None:
        self._mem = _MemoryGraph()
        self._kuzu_db = None
        self._temp_dir: str | None = None

        if _KUZU_AVAILABLE:
            if db_path is None:
                self._temp_dir = tempfile.mkdtemp(prefix="graphstore_")
                # kuzu.Database expects to create the directory itself
                os.rmdir(self._temp_dir)
                db_path = self._temp_dir
                logger.info("KuzuDB using temp directory: %s", db_path)
            self._db_path = db_path
            try:
                self._kuzu_db = kuzu.Database(db_path)
                logger.info("KuzuDB persistence enabled at %s", db_path)
                self._kuzu_init_schema()
                self._hydrate_from_kuzu()
            except Exception as exc:
                raise RuntimeError(f"KuzuDB init failed at {db_path}: {exc}") from exc
        else:
            self._db_path = db_path

    def _kuzu_init_schema(self) -> None:
        """Create KuzuDB node/edge tables if they do not exist."""
        if self._kuzu_db is None:
            return
        conn = kuzu.Connection(self._kuzu_db)
        conn.execute(
            "CREATE NODE TABLE IF NOT EXISTS KGNode "
            "(node_id STRING, state STRING, metadata STRING, created_at DOUBLE, "
            "PRIMARY KEY (node_id))"
        )
        conn.execute(
            "CREATE REL TABLE IF NOT EXISTS KGEdge "
            "(FROM KGNode TO KGNode, weight DOUBLE, traversal_count INT64, last_traversal DOUBLE)"
        )

    def _hydrate_from_kuzu(self) -> None:
        """Hydrate in-memory graph from KuzuDB on startup."""
        if self._kuzu_db is None:
            return
        conn = kuzu.Connection(self._kuzu_db)

        # Load nodes
        try:
            result = conn.execute(
                "MATCH (n:KGNode) "
                "RETURN n.node_id, n.state, n.metadata, n.created_at"
            )
            while result.has_next():
                row = result.get_next()
                node_id, state, metadata_str, created_at = row
                metadata = json.loads(metadata_str) if metadata_str else {}
                node = Node(
                    node_id=node_id,
                    state=state or "Live",
                    created_at=created_at or time.time(),
                    metadata=metadata,
                )
                self._mem._nodes[node_id] = node
        except Exception as exc:
            logger.warning("Failed to hydrate nodes from KuzuDB: %s", exc)

        # Load edges
        try:
            result = conn.execute(
                "MATCH (a:KGNode)-[e:KGEdge]->(b:KGNode) "
                "RETURN a.node_id, b.node_id, e.weight, e.traversal_count, e.last_traversal"
            )
            while result.has_next():
                row = result.get_next()
                src, dst, weight, traversal_count, last_traversal = row
                edge = Edge(
                    source_id=src,
                    dest_id=dst,
                    weight=weight or 1.0,
                    traversal_count=traversal_count or 0,
                    last_traversal=last_traversal or time.time(),
                )
                self._mem._adj[src][dst] = edge
        except Exception as exc:
            logger.warning("Failed to hydrate edges from KuzuDB: %s", exc)

        logger.info(
            "Hydrated %d nodes and %d edge groups from KuzuDB",
            len(self._mem._nodes),
            len(self._mem._adj),
        )

    # ---------------------------------------------------------------------------
    # Write-through mutation methods
    # ---------------------------------------------------------------------------

    def add_node(self, node_id: str, state: str = "Live", metadata: dict | None = None) -> Node:
        with self._mem._lock:
            if self._kuzu_db is not None:
                conn = kuzu.Connection(self._kuzu_db)
                ts = time.time()
                meta_str = json.dumps(metadata or {})
                # Check existence first, then create or update (KuzuDB MERGE semantics)
                check = conn.execute(
                    "MATCH (n:KGNode {node_id: $id}) RETURN n.node_id",
                    parameters={"id": node_id},
                )
                if not check.has_next():
                    conn.execute(
                        "CREATE (:KGNode {node_id: $id, state: $state, "
                        "metadata: $meta, created_at: $ts})",
                        parameters={
                            "id": node_id, "state": state,
                            "meta": meta_str, "ts": ts,
                        },
                    )
                # If node already exists in KuzuDB, leave it unchanged (add_node is idempotent)
            # Update memory (still inside lock)
            if node_id not in self._mem._nodes:
                self._mem._nodes[node_id] = Node(
                    node_id=node_id, state=state, metadata=metadata or {}
                )
            return self._mem._nodes[node_id]

    def upsert_edge(self, source_id: str, dest_id: str, weight: float = 1.0) -> Edge:
        with self._mem._lock:
            # Ensure both nodes exist (writes through to KuzuDB inside add_node)
            self.add_node(source_id)
            self.add_node(dest_id)
            if self._kuzu_db is not None:
                conn = kuzu.Connection(self._kuzu_db)
                ts = time.time()
                # Check if edge exists
                check = conn.execute(
                    "MATCH (a:KGNode {node_id: $src})"
                            "-[e:KGEdge]->"
                            "(b:KGNode {node_id: $dst}) "
                    "RETURN e.weight",
                    parameters={"src": source_id, "dst": dest_id},
                )
                if not check.has_next():
                    conn.execute(
                        "MATCH (a:KGNode {node_id: $src}), "
                        "(b:KGNode {node_id: $dst}) "
                        "CREATE (a)-[:KGEdge {weight: $w, "
                        "traversal_count: 0, last_traversal: $ts}]->(b)",
                        parameters={
                            "src": source_id, "dst": dest_id,
                            "w": weight, "ts": ts,
                        },
                    )
            # Update memory (still inside lock)
            if dest_id not in self._mem._adj[source_id]:
                self._mem._adj[source_id][dest_id] = Edge(
                    source_id=source_id, dest_id=dest_id, weight=weight
                )
            return self._mem._adj[source_id][dest_id]

    def reinforce_edge(self, source_id: str, dest_id: str, quality_score: float) -> None:
        """Reinforce an edge after a scored traversal."""
        with self._mem._lock:
            # Ensure edge exists (writes through inside upsert_edge)
            self.upsert_edge(source_id, dest_id)
            edge = self._mem._adj[source_id][dest_id]
            new_weight = min(edge.weight + quality_score, float(EDGE_DECAY_FLOOR) * 1000)
            new_count = edge.traversal_count + 1
            new_ts = time.time()
            if self._kuzu_db is not None:
                conn = kuzu.Connection(self._kuzu_db)
                conn.execute(
                    "MATCH (a:KGNode {node_id: $src})"
                            "-[e:KGEdge]->"
                            "(b:KGNode {node_id: $dst}) "
                    "SET e.weight = $w, e.traversal_count = $tc, e.last_traversal = $ts",
                    parameters={
                        "src": source_id, "dst": dest_id,
                        "w": new_weight, "tc": new_count, "ts": new_ts,
                    },
                )
            # Update memory (still inside lock)
            edge.weight = new_weight
            edge.traversal_count = new_count
            edge.last_traversal = new_ts

    def decay_edges(self, decay_rate: float = EDGE_DECAY_RATE) -> None:
        """Apply multiplicative decay to all edges, floored at EDGE_DECAY_FLOOR."""
        with self._mem._lock:
            for src, dests in self._mem._adj.items():
                to_remove = []
                for dest, edge in dests.items():
                    new_weight = max(edge.weight * decay_rate, EDGE_DECAY_FLOOR)
                    if new_weight <= EDGE_DECAY_FLOOR:
                        to_remove.append(dest)
                        if self._kuzu_db is not None:
                            conn = kuzu.Connection(self._kuzu_db)
                            conn.execute(
                                "MATCH (a:KGNode {node_id: $src})"
                            "-[e:KGEdge]->"
                            "(b:KGNode {node_id: $dst}) "
                                "DELETE e",
                                parameters={"src": src, "dst": dest},
                            )
                    else:
                        if self._kuzu_db is not None:
                            conn = kuzu.Connection(self._kuzu_db)
                            conn.execute(
                                "MATCH (a:KGNode {node_id: $src})"
                            "-[e:KGEdge]->"
                            "(b:KGNode {node_id: $dst}) "
                                "SET e.weight = $w",
                                parameters={"src": src, "dst": dest, "w": new_weight},
                            )
                        edge.weight = new_weight
                for dest in to_remove:
                    del dests[dest]

    def set_node_state(self, node_id: str, state: str) -> None:
        """Update a node's state in both KuzuDB and memory."""
        with self._mem._lock:
            if self._kuzu_db is not None:
                conn = kuzu.Connection(self._kuzu_db)
                conn.execute(
                    "MATCH (n:KGNode {node_id: $id}) SET n.state = $state",
                    parameters={"id": node_id, "state": state},
                )
            if node_id in self._mem._nodes:
                self._mem._nodes[node_id].state = state

    def get_nodes_by_state(self, state: str) -> list[Node]:
        """Return list of nodes matching the given state."""
        with self._mem._lock:
            return [n for n in self._mem._nodes.values() if n.state == state]

    def log_traversal(
        self,
        session_id: str,
        source_id: str,
        dest_id: str,
        passage_embedding: list[float],
        scores: dict[int, float],
    ) -> None:
        """Log a traversal event for replay and audit."""
        log = TraversalLog(
            session_id=session_id,
            source_id=source_id,
            dest_id=dest_id,
            passage_embedding=passage_embedding,
            scores=scores,
        )
        self._mem.record_traversal(log)

    def bulk_load(self, nodes: list[dict], edges: list[dict]) -> None:
        """Bulk-insert nodes and edges into the graph (write-through to KuzuDB)."""
        with self._mem._lock:
            for n_dict in nodes:
                nid = n_dict["node_id"]
                state = n_dict.get("state", "Live")
                metadata = n_dict.get("metadata", {})
                if self._kuzu_db is not None:
                    conn = kuzu.Connection(self._kuzu_db)
                    ts = time.time()
                    meta_str = json.dumps(metadata)
                    check = conn.execute(
                        "MATCH (n:KGNode {node_id: $id}) RETURN n.node_id",
                        parameters={"id": nid},
                    )
                    if not check.has_next():
                        conn.execute(
                            "CREATE (:KGNode {node_id: $id, "
                            "state: $state, metadata: $meta, "
                            "created_at: $ts})",
                            parameters={
                                "id": nid, "state": state,
                                "meta": meta_str, "ts": ts,
                            },
                        )
                self._mem._nodes[nid] = Node(node_id=nid, state=state, metadata=metadata)

            for e_dict in edges:
                src = e_dict["source_id"]
                dst = e_dict["dest_id"]
                weight = e_dict.get("weight", 1.0)
                traversal_count = e_dict.get("traversal_count", 0)
                # Ensure nodes exist in memory (KuzuDB nodes were created above)
                if src not in self._mem._nodes:
                    self._mem._nodes[src] = Node(node_id=src)
                if dst not in self._mem._nodes:
                    self._mem._nodes[dst] = Node(node_id=dst)
                if self._kuzu_db is not None:
                    conn = kuzu.Connection(self._kuzu_db)
                    ts = time.time()
                    check = conn.execute(
                        "MATCH (a:KGNode {node_id: $src})"
                            "-[e:KGEdge]->"
                            "(b:KGNode {node_id: $dst}) "
                        "RETURN e.weight",
                        parameters={"src": src, "dst": dst},
                    )
                    if check.has_next():
                        conn.execute(
                            "MATCH (a:KGNode {node_id: $src})"
                            "-[e:KGEdge]->"
                            "(b:KGNode {node_id: $dst}) "
                            "SET e.weight = $w, e.traversal_count = $tc",
                            parameters={"src": src, "dst": dst, "w": weight, "tc": traversal_count},
                        )
                    else:
                        conn.execute(
                            "MATCH (a:KGNode {node_id: $src}), "
                            "(b:KGNode {node_id: $dst}) "
                            "CREATE (a)-[:KGEdge {weight: $w, "
                            "traversal_count: $tc, "
                            "last_traversal: $ts}]->(b)",
                            parameters={
                                "src": src, "dst": dst,
                                "w": weight, "tc": traversal_count,
                                "ts": ts,
                            },
                        )
                self._mem._adj[src][dst] = Edge(
                    source_id=src,
                    dest_id=dst,
                    weight=weight,
                    traversal_count=traversal_count,
                )

    # ---------------------------------------------------------------------------
    # Read-only delegation to _MemoryGraph
    # ---------------------------------------------------------------------------

    def betweenness_centrality(self, node_id: str) -> float:
        """Compute betweenness centrality for a node (Brandes algorithm)."""
        scores = self._mem.brandes_betweenness()
        return scores.get(node_id, 0.0)

    def outgoing_edge_weight_sum(self, node_id: str) -> float:
        """Sum of outgoing edge weights for a node."""
        return self._mem.outgoing_edge_weight_sum(node_id)

    def neighbours(self, node_id: str) -> list[str]:
        return self._mem.neighbours(node_id)

    def bfs_path(self, source_id: str, dest_id: str) -> list[str] | None:
        return self._mem.bfs_path(source_id, dest_id)

    def sample_recent_sessions(self, n: int = 10) -> list[dict]:
        """Sample recently-completed sessions for validator scoring."""
        return self._mem.sample_recent_sessions(n)

    def get_live_node_ids(self) -> list[str]:
        """Return all node IDs in Live state."""
        return self._mem.get_live_node_ids()

    def get_connected_node_ids(self) -> list[str]:
        """Return IDs of all nodes that participate in at least one outgoing edge."""
        return self._mem.get_connected_node_ids()

    def get_node(self, node_id: str) -> Node | None:
        """Return a single node by ID, or None."""
        return self._mem.get_node(node_id)

    def get_all_nodes(self) -> list[Node]:
        """Return all nodes (all states)."""
        with self._mem._lock:
            return list(self._mem._nodes.values())

    def get_all_edges(self) -> list[Edge]:
        """Return all edges."""
        with self._mem._lock:
            return [
                edge
                for dests in self._mem._adj.values()
                for edge in dests.values()
            ]

    def stats(self) -> dict:
        """Return graph statistics."""
        return self._mem.stats()
