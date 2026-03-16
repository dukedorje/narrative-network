"""Integration tests for the production gateway path (create_app()).

Patches bt.Dendrite inside orchestrator.gateway so MockDendrite is used,
then exercises POST /enter, POST /hop, GET /session/{id}, GET /healthz
against the real FastAPI app created by create_app().

Usage:
    uv run pytest tests/integration/test_production_gateway.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from tests.conftest import (
    FakeEmbedder,
    MockDendrite,
    MockMetagraph,
    MockMinerNetwork,
    MockSubtensor,
    MockWallet,
)


# ---------------------------------------------------------------------------
# Test graph topology
# ---------------------------------------------------------------------------

TEST_NODE_IDS = [
    "quantum-mechanics",
    "thermodynamics",
    "information-theory",
    "consciousness-studies",
    "evolutionary-biology",
]


def _build_graph_store():
    from subnet.graph_store import GraphStore

    gs = GraphStore(db_path=None)
    for nid in TEST_NODE_IDS:
        gs.add_node(nid, state="Live", metadata={"description": f"Domain of {nid}"})
    # Build a connected ring so every node has neighbours
    for i, nid in enumerate(TEST_NODE_IDS):
        next_nid = TEST_NODE_IDS[(i + 1) % len(TEST_NODE_IDS)]
        gs.upsert_edge(nid, next_nid, weight=1.0)
        gs.upsert_edge(next_nid, nid, weight=1.0)
    return gs


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def prod_app():
    """Create the production FastAPI app with all dependencies mocked.

    bt.Dendrite is patched inside orchestrator.gateway so that
    create_app() picks up MockDendrite instead of the real one.
    """
    from orchestrator.gateway import create_app
    from orchestrator.router import Router
    from orchestrator.safety_guard import PathSafetyGuard

    graph_store = _build_graph_store()
    embedder = FakeEmbedder(dim=768)

    metagraph = MockMetagraph(
        n=4,
        hotkeys=["validator-hotkey", "miner-1-hotkey", "miner-2-hotkey", "miner-3-hotkey"],
        stakes=[1000.0, 100.0, 100.0, 100.0],
        validator_permit=[True, False, False, False],
        axon_serving=[True, True, True, True],
    )
    wallet = MockWallet(hotkey_address="validator-hotkey")
    subtensor = MockSubtensor(metagraph=metagraph)

    mock_dendrite = MockDendrite(wallet=wallet)
    MockMinerNetwork(
        n_miners=len(TEST_NODE_IDS),
        metagraph=metagraph,
        dendrite=mock_dendrite,
        embedder=embedder,
        graph_node_ids=TEST_NODE_IDS,
    )

    router = Router(graph_store=graph_store, metagraph=metagraph)
    safety_guard = PathSafetyGuard()

    with patch("orchestrator.gateway.bt.Dendrite", return_value=mock_dendrite):
        app = create_app(
            graph_store=graph_store,
            embedder=embedder,
            router=router,
            safety_guard=safety_guard,
            wallet=wallet,
            subtensor=subtensor,
            metagraph=metagraph,
        )

    # Expose the dendrite on the app for test assertions
    app.state.mock_dendrite = mock_dendrite

    # Yield inside the MIN_HOP_WORDS patch so check_passage passes for short
    # mock narratives (MockMinerNetwork produces ~54 words; production min is 100).
    with patch("orchestrator.safety_guard.MIN_HOP_WORDS", 0):
        yield app


@pytest.fixture
async def prod_client(prod_app) -> httpx.AsyncClient:
    """ASGI test client wired to the production app."""
    from httpx import ASGITransport

    transport = ASGITransport(app=prod_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dendrite(prod_app) -> MockDendrite:
    return prod_app.state.mock_dendrite


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_prod_healthz(prod_client: httpx.AsyncClient, prod_app):
    """GET /healthz returns ok with session count fields."""
    resp = await prod_client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "active_sessions" in data
    assert "total_sessions" in data
    assert data["active_sessions"] == 0
    assert data["total_sessions"] == 0


async def test_prod_enter_dispatches_knowledge_query(
    prod_client: httpx.AsyncClient, prod_app
):
    """POST /enter triggers KnowledgeQuery on MockDendrite and returns a session."""
    dendrite = _dendrite(prod_app)

    resp = await prod_client.post("/enter", json={"query_text": "quantum entanglement"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Session shape
    assert data["session_id"]
    assert data["state"] == "active"
    assert data["current_node_id"]
    assert len(data["player_path"]) == 1
    assert data["player_path"][0] == data["current_node_id"]
    assert data["narrative_passage"]
    assert isinstance(data["choice_cards"], list)
    assert len(data["choice_cards"]) > 0

    # Dendrite received at least one KnowledgeQuery call
    kq_calls = [c for c in dendrite.call_log if c["synapse_type"] == "KnowledgeQuery"]
    assert len(kq_calls) >= 1, "Expected at least one KnowledgeQuery dispatch"
    # All active axons should have been queried
    assert kq_calls[0]["axon_count"] > 0


async def test_prod_hop_dispatches_narrative_hop(
    prod_client: httpx.AsyncClient, prod_app
):
    """POST /hop after enter dispatches a NarrativeHop synapse."""
    dendrite = _dendrite(prod_app)

    enter_resp = await prod_client.post("/enter", json={"query_text": "thermodynamics"})
    assert enter_resp.status_code == 200, enter_resp.text
    enter_data = enter_resp.json()
    session_id = enter_data["session_id"]
    dest = enter_data["choice_cards"][0]["destination_node_id"]

    hop_resp = await prod_client.post("/hop", json={
        "session_id": session_id,
        "destination_node_id": dest,
    })
    assert hop_resp.status_code == 200, hop_resp.text
    hop_data = hop_resp.json()

    assert hop_data["session_id"] == session_id
    assert hop_data["current_node_id"] == dest
    assert hop_data["narrative_passage"]

    # Dendrite received at least one NarrativeHop call (from either enter or hop)
    nh_calls = [c for c in dendrite.call_log if c["synapse_type"] == "NarrativeHop"]
    assert len(nh_calls) >= 2, "Expected NarrativeHop dispatches for enter + hop"


async def test_prod_enter_hop_full_flow(prod_client: httpx.AsyncClient, prod_app):
    """Enter + hop: verify path grows and call_log shows both synapse types."""
    dendrite = _dendrite(prod_app)
    initial_log_len = len(dendrite.call_log)

    enter_resp = await prod_client.post(
        "/enter", json={"query_text": "information theory and entropy"}
    )
    assert enter_resp.status_code == 200, enter_resp.text
    enter_data = enter_resp.json()

    session_id = enter_data["session_id"]
    entry_node = enter_data["current_node_id"]
    dest = enter_data["choice_cards"][0]["destination_node_id"]

    hop_resp = await prod_client.post("/hop", json={
        "session_id": session_id,
        "destination_node_id": dest,
    })
    assert hop_resp.status_code == 200, hop_resp.text
    hop_data = hop_resp.json()

    # Path grew
    assert hop_data["player_path"] == [entry_node, dest]
    assert hop_data["current_node_id"] == dest
    assert hop_data["state"] in ("active", "terminal")

    # Both synapse types appear in call_log after our test started
    new_calls = dendrite.call_log[initial_log_len:]
    synapse_types = {c["synapse_type"] for c in new_calls}
    assert "KnowledgeQuery" in synapse_types, "Missing KnowledgeQuery in call_log"
    assert "NarrativeHop" in synapse_types, "Missing NarrativeHop in call_log"


async def test_prod_enter_no_miners_503(prod_app):
    """POST /enter returns 503 when no active axons are in the metagraph."""
    from orchestrator.gateway import create_app
    from orchestrator.router import Router
    from orchestrator.safety_guard import PathSafetyGuard
    from httpx import ASGITransport

    graph_store = _build_graph_store()
    embedder = FakeEmbedder(dim=768)

    # All axons have ip="0.0.0.0" — none are active
    empty_metagraph = MockMetagraph(
        n=3,
        axon_serving=[True, True, True],
    )
    # Override axon IPs to 0.0.0.0 so they are filtered out by the gateway
    for axon in empty_metagraph.axons:
        axon.ip = "0.0.0.0"

    wallet = MockWallet()
    subtensor = MockSubtensor(metagraph=empty_metagraph)
    mock_dendrite = MockDendrite(wallet=wallet)

    router = Router(graph_store=graph_store, metagraph=empty_metagraph)
    safety_guard = PathSafetyGuard()

    with patch("orchestrator.gateway.bt.Dendrite", return_value=mock_dendrite):
        app = create_app(
            graph_store=graph_store,
            embedder=embedder,
            router=router,
            safety_guard=safety_guard,
            wallet=wallet,
            subtensor=subtensor,
            metagraph=empty_metagraph,
        )

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/enter", json={"query_text": "anything"})
        assert resp.status_code == 503
        assert "No active miners" in resp.json()["detail"]


async def test_prod_session_read(prod_client: httpx.AsyncClient):
    """GET /session/{id} after enter returns consistent state."""
    enter_resp = await prod_client.post("/enter", json={"query_text": "consciousness"})
    assert enter_resp.status_code == 200, enter_resp.text
    enter_data = enter_resp.json()
    session_id = enter_data["session_id"]

    sess_resp = await prod_client.get(f"/session/{session_id}")
    assert sess_resp.status_code == 200
    sess = sess_resp.json()

    assert sess["session_id"] == session_id
    assert sess["state"] == "active"
    assert sess["current_node_id"] == enter_data["current_node_id"]
    assert sess["player_path"] == enter_data["player_path"]
    assert "created_at" in sess
    assert "updated_at" in sess
