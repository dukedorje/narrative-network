"""Integration tests for Router with mock metagraph.

Tests rank_entry_nodes() and resolve_narrative_miner() using MockMetagraph
and MockAxonInfo from conftest.py.

Usage:
    uv run pytest tests/integration/test_router_integration.py -v
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from tests.conftest import MockAxonInfo, MockMetagraph


# ---------------------------------------------------------------------------
# rank_entry_nodes
# ---------------------------------------------------------------------------


def test_rank_entry_nodes_sorts_by_similarity(graph_store, mock_metagraph):
    """Results are sorted descending by domain_similarity."""
    from orchestrator.router import Router
    from subnet.protocol import KnowledgeQuery

    router = Router(graph_store=graph_store, metagraph=mock_metagraph)

    resp_a = KnowledgeQuery()
    resp_a.domain_similarity = 0.9
    resp_a.node_id = "node-a"

    resp_b = KnowledgeQuery()
    resp_b.domain_similarity = 0.5
    resp_b.node_id = "node-b"

    resp_c = KnowledgeQuery()
    resp_c.domain_similarity = 0.7
    resp_c.node_id = "node-c"

    result = router.rank_entry_nodes(query_embedding=[], responses=[resp_a, resp_b, resp_c])

    assert result == ["node-a", "node-c", "node-b"]


def test_rank_entry_nodes_filters_none_node_id(graph_store, mock_metagraph):
    """Responses with node_id=None are excluded from results."""
    from orchestrator.router import Router
    from subnet.protocol import KnowledgeQuery

    router = Router(graph_store=graph_store, metagraph=mock_metagraph)

    resp_valid = KnowledgeQuery()
    resp_valid.domain_similarity = 0.8
    resp_valid.node_id = "node-x"

    resp_none = KnowledgeQuery()
    resp_none.domain_similarity = 0.95
    resp_none.node_id = None

    result = router.rank_entry_nodes(query_embedding=[], responses=[resp_valid, resp_none])

    assert "node-x" in result
    assert None not in result
    assert len(result) == 1


# ---------------------------------------------------------------------------
# resolve_narrative_miner
# ---------------------------------------------------------------------------


def test_resolve_narrative_miner_returns_highest_stake(graph_store):
    """resolve_narrative_miner returns the axon with the highest stake."""
    from orchestrator.router import Router

    metagraph = MockMetagraph(
        n=4,
        stakes=[1000.0, 50.0, 200.0, 150.0],
        axon_serving=[True, True, True, True],
    )

    router = Router(graph_store=graph_store, metagraph=metagraph)
    result = router.resolve_narrative_miner(destination_node_id="node-0")

    assert result is not None
    # UID 0 has stake 1000.0 — its axon ip should be the default serving ip
    assert result.ip == "127.0.0.1"
    assert result.uid == 0


def test_resolve_narrative_miner_skips_non_serving(graph_store):
    """Axons with ip='0.0.0.0' are skipped; highest-stake serving axon is returned."""
    from orchestrator.router import Router

    metagraph = MockMetagraph(n=4, stakes=[1000.0, 50.0, 200.0, 150.0])
    # Override UID 0 (highest stake) to be non-serving
    metagraph.axons[0] = MockAxonInfo(ip="0.0.0.0", port=8091, uid=0)

    router = Router(graph_store=graph_store, metagraph=metagraph)
    result = router.resolve_narrative_miner(destination_node_id="node-0")

    assert result is not None
    # UID 0 is skipped; next highest stake is UID 2 (200.0)
    assert result.uid == 2


def test_resolve_narrative_miner_empty_metagraph(graph_store):
    """Returns None when all axons have ip='0.0.0.0' (none are serving)."""
    from orchestrator.router import Router

    metagraph = MockMetagraph(n=3, stakes=[500.0, 300.0, 100.0])
    for i in range(3):
        metagraph.axons[i] = MockAxonInfo(ip="0.0.0.0", port=8091, uid=i)

    router = Router(graph_store=graph_store, metagraph=metagraph)
    result = router.resolve_narrative_miner(destination_node_id="node-0")

    assert result is None
