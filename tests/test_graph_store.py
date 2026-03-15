"""Unit tests for subnet.graph_store.GraphStore."""

from __future__ import annotations

import pytest

from subnet.config import EDGE_DECAY_FLOOR, EDGE_DECAY_RATE
from subnet.graph_store import GraphStore


@pytest.fixture
def gs():
    """Fresh in-memory GraphStore for each test."""
    return GraphStore(db_path=None)


# ---------------------------------------------------------------------------
# Node tests
# ---------------------------------------------------------------------------


def test_add_node_and_get(gs):
    node = gs.add_node("alpha", state="Live", metadata={"domain": "science"})
    assert node.node_id == "alpha"
    assert node.state == "Live"
    assert node.metadata == {"domain": "science"}
    assert gs._mem.get_node("alpha") is node


def test_add_node_idempotent(gs):
    n1 = gs.add_node("alpha")
    n2 = gs.add_node("alpha")
    assert n1 is n2
    assert len(gs._mem._nodes) == 1


# ---------------------------------------------------------------------------
# Edge tests
# ---------------------------------------------------------------------------


def test_upsert_edge_creates_nodes(gs):
    edge = gs.upsert_edge("a", "b", weight=2.5)
    assert edge.source_id == "a"
    assert edge.dest_id == "b"
    assert edge.weight == 2.5
    # Both nodes auto-created
    assert gs._mem.get_node("a") is not None
    assert gs._mem.get_node("b") is not None


def test_reinforce_edge(gs):
    gs.upsert_edge("a", "b", weight=1.0)
    gs.reinforce_edge("a", "b", quality_score=0.5)
    edge = gs._mem._adj["a"]["b"]
    assert edge.weight == pytest.approx(1.5)
    assert edge.traversal_count == 1


def test_reinforce_edge_cap(gs):
    """Weight is capped at EDGE_DECAY_FLOOR * 1000 = 10.0."""
    gs.upsert_edge("a", "b", weight=9.9)
    gs.reinforce_edge("a", "b", quality_score=5.0)
    edge = gs._mem._adj["a"]["b"]
    assert edge.weight == pytest.approx(EDGE_DECAY_FLOOR * 1000)


def test_decay_edges(gs):
    gs.upsert_edge("x", "y", weight=2.0)
    gs.decay_edges(decay_rate=0.5)
    edge = gs._mem._adj["x"]["y"]
    # 2.0 * 0.5 = 1.0; above floor so not pruned
    assert edge.weight == pytest.approx(1.0)


def test_decay_prunes_at_floor(gs):
    """An edge already at EDGE_DECAY_FLOOR gets pruned after decay."""
    gs.upsert_edge("x", "y", weight=EDGE_DECAY_FLOOR)
    # Any decay rate will keep it at floor and trigger pruning
    gs._mem.decay_all(decay_rate=EDGE_DECAY_RATE)
    assert "y" not in gs._mem._adj.get("x", {})


def test_neighbours(gs):
    gs.upsert_edge("a", "b")
    gs.upsert_edge("a", "c")
    nbs = gs.neighbours("a")
    assert set(nbs) == {"b", "c"}


def test_bfs_path_exists(gs):
    gs.upsert_edge("a", "b")
    gs.upsert_edge("b", "c")
    path = gs.bfs_path("a", "c")
    assert path == ["a", "b", "c"]


def test_bfs_path_none(gs):
    gs.add_node("isolated")
    gs.add_node("other")
    assert gs.bfs_path("isolated", "other") is None


# ---------------------------------------------------------------------------
# Centrality
# ---------------------------------------------------------------------------


def test_betweenness_centrality_bridge(gs):
    """Bridge node (b) on only path a->b->c has higher centrality than leaves."""
    gs.upsert_edge("a", "b")
    gs.upsert_edge("b", "c")
    cb_a = gs.betweenness_centrality("a")
    cb_b = gs.betweenness_centrality("b")
    cb_c = gs.betweenness_centrality("c")
    assert cb_b > cb_a
    assert cb_b > cb_c


def test_betweenness_centrality_single_node(gs):
    gs.add_node("solo")
    assert gs.betweenness_centrality("solo") == 0.0


# ---------------------------------------------------------------------------
# Bulk load
# ---------------------------------------------------------------------------


def test_bulk_load(gs):
    nodes = [{"node_id": "n1"}, {"node_id": "n2", "state": "Incubating"}]
    edges = [{"source_id": "n1", "dest_id": "n2", "weight": 3.0}]
    gs.bulk_load(nodes, edges)
    s = gs.stats()
    assert s["node_count"] == 2
    assert s["edge_count"] == 1
    assert gs._mem.get_node("n2").state == "Incubating"
    assert gs._mem._adj["n1"]["n2"].weight == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Traversal log
# ---------------------------------------------------------------------------


def test_log_and_sample_traversals(gs):
    gs.log_traversal("sess-1", "a", "b", [0.1, 0.2], {1: 0.8})
    gs.log_traversal("sess-2", "b", "c", [0.3, 0.4], {2: 0.9})
    samples = gs.sample_recent_sessions(n=10)
    assert len(samples) == 2
    session_ids = {s["session_id"] for s in samples}
    assert session_ids == {"sess-1", "sess-2"}


def test_sample_sessions_excludes_embedding(gs):
    gs.log_traversal("sess-1", "a", "b", [0.1, 0.2, 0.3], {1: 0.7})
    samples = gs.sample_recent_sessions(n=1)
    assert len(samples) == 1
    assert "passage_embedding" not in samples[0]


def test_sample_recent_sessions_order(gs):
    """sample_recent_sessions returns most recent first."""
    import time

    gs.log_traversal("old", "a", "b", [], {})
    time.sleep(0.01)
    gs.log_traversal("new", "b", "c", [], {})
    samples = gs.sample_recent_sessions(n=2)
    assert samples[0]["session_id"] == "new"


# ---------------------------------------------------------------------------
# Live nodes
# ---------------------------------------------------------------------------


def test_get_live_node_ids(gs):
    gs.add_node("live1", state="Live")
    gs.add_node("incub", state="Incubating")
    gs.add_node("live2", state="Live")
    live = gs.get_live_node_ids()
    assert set(live) == {"live1", "live2"}
    assert "incub" not in live


# ---------------------------------------------------------------------------
# Outgoing edge weight sum
# ---------------------------------------------------------------------------


def test_outgoing_edge_weight_sum(gs):
    gs.upsert_edge("a", "b", weight=1.5)
    gs.upsert_edge("a", "c", weight=2.5)
    total = gs.outgoing_edge_weight_sum("a")
    assert total == pytest.approx(4.0)


def test_outgoing_edge_weight_sum_no_edges(gs):
    gs.add_node("lonely")
    assert gs.outgoing_edge_weight_sum("lonely") == pytest.approx(0.0)
