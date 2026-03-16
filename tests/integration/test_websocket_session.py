"""Integration tests for WebSocket session and OrchestratorSession.

Part 1: WebSocket endpoint tests via create_app() + Starlette TestClient.
Part 2: OrchestratorSession direct unit tests with MockDendrite + MockMinerNetwork.

Usage:
    uv run pytest tests/integration/test_websocket_session.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from tests.conftest import (
    FakeEmbedder,
    MockAxonInfo,
    MockDendrite,
    MockMetagraph,
    MockMinerNetwork,
    MockSubtensor,
    MockWallet,
)


# ---------------------------------------------------------------------------
# Shared test graph topology
# ---------------------------------------------------------------------------

TEST_NODE_IDS = ["node-0", "node-1", "node-2", "node-3", "node-4"]


def _build_graph_store():
    from subnet.graph_store import GraphStore

    gs = GraphStore(db_path=None)
    for nid in TEST_NODE_IDS:
        gs.add_node(nid, state="Live", metadata={"description": f"Domain of {nid}"})
    # Connected ring so every node has neighbours
    for i, nid in enumerate(TEST_NODE_IDS):
        next_nid = TEST_NODE_IDS[(i + 1) % len(TEST_NODE_IDS)]
        gs.upsert_edge(nid, next_nid, weight=1.0)
        gs.upsert_edge(next_nid, nid, weight=1.0)
    return gs


# ---------------------------------------------------------------------------
# Shared app factory
# ---------------------------------------------------------------------------


def _build_prod_app(mock_dendrite: MockDendrite, embedder: FakeEmbedder):
    """Build create_app() with all dependencies mocked, return (app, dendrite)."""
    from orchestrator.gateway import create_app
    from orchestrator.router import Router
    from orchestrator.safety_guard import PathSafetyGuard

    graph_store = _build_graph_store()

    metagraph = MockMetagraph(
        n=4,
        hotkeys=["validator-hotkey", "miner-1-hotkey", "miner-2-hotkey", "miner-3-hotkey"],
        stakes=[1000.0, 100.0, 100.0, 100.0],
        validator_permit=[True, False, False, False],
        axon_serving=[True, True, True, True],
    )
    wallet = MockWallet(hotkey_address="validator-hotkey")
    subtensor = MockSubtensor(metagraph=metagraph)

    MockMinerNetwork(
        n_miners=len(TEST_NODE_IDS),
        metagraph=metagraph,
        dendrite=mock_dendrite,
        embedder=embedder,
        graph_node_ids=TEST_NODE_IDS,
    )

    router = Router(graph_store=graph_store, metagraph=metagraph)
    safety_guard = PathSafetyGuard()

    with (
        patch("orchestrator.gateway.bt.Dendrite", return_value=mock_dendrite),
        patch("orchestrator.safety_guard.MIN_HOP_WORDS", 0),
    ):
        app = create_app(
            graph_store=graph_store,
            embedder=embedder,
            router=router,
            safety_guard=safety_guard,
            wallet=wallet,
            subtensor=subtensor,
            metagraph=metagraph,
        )

    return app


# ---------------------------------------------------------------------------
# Part 1: WebSocket tests
# ---------------------------------------------------------------------------


@pytest.fixture
def ws_client():
    """Synchronous Starlette TestClient with the production app.

    MIN_HOP_WORDS is patched to 0 for the lifetime of the fixture so
    MockMinerNetwork passage lengths don't trip the safety guard.
    """
    embedder = FakeEmbedder(dim=768)
    wallet = MockWallet(hotkey_address="validator-hotkey")
    mock_dendrite = MockDendrite(wallet=wallet)
    app = _build_prod_app(mock_dendrite, embedder)
    app.state.mock_dendrite = mock_dendrite
    with patch("orchestrator.safety_guard.MIN_HOP_WORDS", 0):
        yield TestClient(app, raise_server_exceptions=True)


def test_ws_connect_and_receive_state(ws_client: TestClient):
    """Connect to WS after creating a session via POST /enter; receive initial state."""
    # Create a session first
    enter_resp = ws_client.post("/enter", json={"query_text": "quantum mechanics"})
    assert enter_resp.status_code == 200, enter_resp.text
    session_id = enter_resp.json()["session_id"]

    # Connect to the WebSocket for that session
    with ws_client.websocket_connect(f"/session/{session_id}/live") as ws:
        state = ws.receive_json()

    assert state["session_id"] == session_id
    assert state["state"] == "active"
    assert isinstance(state["player_path"], list)
    assert len(state["player_path"]) >= 1


def test_ws_hop_via_websocket(ws_client: TestClient):
    """Send a hop request over WebSocket and receive a narrative result."""
    # Create a session
    enter_resp = ws_client.post("/enter", json={"query_text": "thermodynamics"})
    assert enter_resp.status_code == 200, enter_resp.text
    enter_data = enter_resp.json()
    session_id = enter_data["session_id"]
    dest = enter_data["choice_cards"][0]["destination_node_id"]

    with ws_client.websocket_connect(f"/session/{session_id}/live") as ws:
        # Consume initial state push
        initial = ws.receive_json()
        assert initial["session_id"] == session_id

        # Send a hop
        ws.send_json({"destination_node_id": dest})
        result = ws.receive_json()

    # Result should have narrative_passage or at minimum session_id
    assert "session_id" in result
    assert result.get("narrative_passage") or result.get("error") is None, (
        f"Hop result missing narrative_passage: {result}"
    )
    assert result.get("narrative_passage"), f"Expected narrative_passage in hop result: {result}"


def test_ws_nonexistent_session_closes(ws_client: TestClient):
    """Connecting to WS for an unknown session_id should close with code 4004."""
    with pytest.raises(Exception):
        # Starlette TestClient raises when the server closes with an error code
        with ws_client.websocket_connect("/session/nonexistent-session-id/live") as ws:
            ws.receive_json()


# ---------------------------------------------------------------------------
# Part 2: OrchestratorSession direct tests
# ---------------------------------------------------------------------------


@pytest.fixture
def session_dendrite():
    wallet = MockWallet(hotkey_address="validator-hotkey")
    return MockDendrite(wallet=wallet)


@pytest.fixture
def session_metagraph():
    return MockMetagraph(
        n=4,
        hotkeys=["validator-hotkey", "miner-1-hotkey", "miner-2-hotkey", "miner-3-hotkey"],
        stakes=[1000.0, 100.0, 100.0, 100.0],
        validator_permit=[True, False, False, False],
        axon_serving=[True, True, True, True],
    )


@pytest.fixture
def wired_network(session_dendrite, session_metagraph):
    """MockMinerNetwork wired to session_dendrite with TEST_NODE_IDS."""
    embedder = FakeEmbedder(dim=768)
    MockMinerNetwork(
        n_miners=len(TEST_NODE_IDS),
        metagraph=session_metagraph,
        dendrite=session_dendrite,
        embedder=embedder,
        graph_node_ids=TEST_NODE_IDS,
    )
    return session_dendrite


async def test_session_enter_fetches_chunks_and_generates(
    wired_network: MockDendrite, session_metagraph: MockMetagraph
):
    """enter() causes both KnowledgeQuery and NarrativeHop to appear in call_log."""
    from orchestrator.safety_guard import PathSafetyGuard
    from orchestrator.session import OrchestratorSession

    mock_dendrite = wired_network
    with patch("orchestrator.safety_guard.MIN_HOP_WORDS", 0):
        safety_guard = PathSafetyGuard()
        session = OrchestratorSession(
            dendrite=mock_dendrite,
            metagraph=session_metagraph,
            safety_guard=safety_guard,
        )

        embedder = FakeEmbedder(dim=768)
        query_embedding = embedder.embed_one("test query about knowledge")
        entry_axon = MockAxonInfo(is_serving=True, ip="127.0.0.1", port=8091, uid=1)

        result = await session.enter(
            query_text="test query about knowledge",
            query_embedding=query_embedding,
            entry_node_id="node-0",
            axon=entry_axon,
        )

    assert "error" not in result, f"enter() returned error: {result}"
    assert result["session_id"] == session.session_id
    assert result["state"] == "active"
    assert result["current_node_id"] == "node-0"
    assert result["player_path"] == ["node-0"]
    assert result["narrative_passage"]

    synapse_types = {c["synapse_type"] for c in mock_dendrite.call_log}
    assert "KnowledgeQuery" in synapse_types, f"Missing KnowledgeQuery in call_log: {mock_dendrite.call_log}"
    assert "NarrativeHop" in synapse_types, f"Missing NarrativeHop in call_log: {mock_dendrite.call_log}"


async def test_session_hop_sends_narrative_hop(
    wired_network: MockDendrite, session_metagraph: MockMetagraph
):
    """After enter(), hop() adds another NarrativeHop to call_log."""
    from orchestrator.safety_guard import PathSafetyGuard
    from orchestrator.session import OrchestratorSession

    mock_dendrite = wired_network
    with patch("orchestrator.safety_guard.MIN_HOP_WORDS", 0):
        safety_guard = PathSafetyGuard()
        session = OrchestratorSession(
            dendrite=mock_dendrite,
            metagraph=session_metagraph,
            safety_guard=safety_guard,
        )

        embedder = FakeEmbedder(dim=768)
        query_embedding = embedder.embed_one("information theory")
        entry_axon = MockAxonInfo(is_serving=True, ip="127.0.0.1", port=8091, uid=1)

        enter_result = await session.enter(
            query_text="information theory",
            query_embedding=query_embedding,
            entry_node_id="node-0",
            axon=entry_axon,
        )
        assert "error" not in enter_result, f"enter() failed: {enter_result}"

        nh_count_before = sum(
            1 for c in mock_dendrite.call_log if c["synapse_type"] == "NarrativeHop"
        )

        hop_axon = MockAxonInfo(is_serving=True, ip="127.0.0.1", port=8092, uid=2)
        hop_result = await session.hop(destination_node_id="node-1", axon=hop_axon)

    assert "error" not in hop_result, f"hop() returned error: {hop_result}"
    assert hop_result["current_node_id"] == "node-1"
    assert hop_result["player_path"] == ["node-0", "node-1"]
    assert hop_result["narrative_passage"]

    nh_count_after = sum(
        1 for c in mock_dendrite.call_log if c["synapse_type"] == "NarrativeHop"
    )
    assert nh_count_after > nh_count_before, "hop() should have dispatched at least one more NarrativeHop"


async def test_session_safety_guard_blocks_revisit(
    wired_network: MockDendrite, session_metagraph: MockMetagraph
):
    """Attempting to hop back to an already-visited node returns an error dict."""
    from orchestrator.safety_guard import PathSafetyGuard
    from orchestrator.session import OrchestratorSession

    mock_dendrite = wired_network
    with patch("orchestrator.safety_guard.MIN_HOP_WORDS", 0):
        safety_guard = PathSafetyGuard()
        session = OrchestratorSession(
            dendrite=mock_dendrite,
            metagraph=session_metagraph,
            safety_guard=safety_guard,
        )

        embedder = FakeEmbedder(dim=768)
        query_embedding = embedder.embed_one("consciousness studies")
        entry_axon = MockAxonInfo(is_serving=True, ip="127.0.0.1", port=8091, uid=1)

        enter_result = await session.enter(
            query_text="consciousness studies",
            query_embedding=query_embedding,
            entry_node_id="node-0",
            axon=entry_axon,
        )
        assert "error" not in enter_result, f"enter() failed: {enter_result}"

        # Hop forward to node-1
        hop_axon = MockAxonInfo(is_serving=True, ip="127.0.0.1", port=8092, uid=2)
        hop_result = await session.hop(destination_node_id="node-1", axon=hop_axon)
        assert "error" not in hop_result, f"first hop() failed: {hop_result}"
        assert session.player_path == ["node-0", "node-1"]

        # Attempt to hop back to node-0 (already visited)
        revisit_result = await session.hop(destination_node_id="node-0", axon=entry_axon)

    assert "error" in revisit_result, (
        f"Expected error when revisiting node-0, got: {revisit_result}"
    )
    assert "already visited" in revisit_result["error"].lower(), (
        f"Error message should mention 'already visited': {revisit_result['error']}"
    )
    # Path must not have grown
    assert session.player_path == ["node-0", "node-1"]
