"""Graph store for the living knowledge graph.

_MemoryGraph provides thread-safe in-process storage with adjacency lists.
GraphStore wraps _MemoryGraph and optionally persists to KuzuDB.
"""

from __future__ import annotations

import collections
import logging
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
    """Graph store with in-memory core and optional KuzuDB persistence.

    Args:
        db_path: Path for KuzuDB persistence. Pass None to disable.
    """

    def __init__(self, db_path: str | None = "./graph.db") -> None:
        self._mem = _MemoryGraph()
        self._db_path = db_path
        self._kuzu_db = None

        if db_path is not None and _KUZU_AVAILABLE:
            try:
                self._kuzu_db = kuzu.Database(db_path)
                logger.info("KuzuDB persistence enabled at %s", db_path)
                self._kuzu_init_schema()
            except Exception as exc:
                logger.warning("KuzuDB init failed (%s) — running memory-only", exc)
                self._kuzu_db = None

    def _kuzu_init_schema(self) -> None:
        """Create KuzuDB node/edge tables if they do not exist."""
        if self._kuzu_db is None:
            return
        conn = kuzu.Connection(self._kuzu_db)
        conn.execute(
            "CREATE NODE TABLE IF NOT EXISTS KGNode "
            "(node_id STRING, state STRING, PRIMARY KEY (node_id))"
        )
        conn.execute(
            "CREATE REL TABLE IF NOT EXISTS KGEdge "
            "(FROM KGNode TO KGNode, weight DOUBLE, traversal_count INT64)"
        )

    # --- Delegation to _MemoryGraph ---

    def add_node(self, node_id: str, state: str = "Live", metadata: dict | None = None) -> Node:
        return self._mem.add_node(node_id, state=state, metadata=metadata)

    def upsert_edge(self, source_id: str, dest_id: str, weight: float = 1.0) -> Edge:
        return self._mem.upsert_edge(source_id, dest_id, weight)

    def reinforce_edge(self, source_id: str, dest_id: str, quality_score: float) -> None:
        """Reinforce an edge after a scored traversal."""
        self._mem.reinforce_edge(source_id, dest_id, quality_score)

    def decay_edges(self, decay_rate: float = EDGE_DECAY_RATE) -> None:
        """Apply multiplicative decay to all edges, floored at EDGE_DECAY_FLOOR."""
        self._mem.decay_all(decay_rate)

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

    def sample_recent_sessions(self, n: int = 10) -> list[dict]:
        """Sample recently-completed sessions for validator scoring."""
        return self._mem.sample_recent_sessions(n)

    def get_live_node_ids(self) -> list[str]:
        """Return all node IDs in Live state."""
        return self._mem.get_live_node_ids()

    def bulk_load(self, nodes: list[dict], edges: list[dict]) -> None:
        """Bulk-insert nodes and edges into the in-memory graph."""
        self._mem.bulk_load(nodes, edges)

    def stats(self) -> dict:
        """Return graph statistics."""
        return self._mem.stats()
