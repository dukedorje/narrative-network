"""Integration tests — exercise the full gateway HTTP flow with local stack.

Runs create_dev_app() with fake embedder + narrator. Tests the real FastAPI
routes, session management, safety guards, graph endpoints, and arbiter
integration — everything except the actual LLM and SentenceTransformer.

Usage:
    uv run pytest tests/integration/ -v
"""

import httpx
import pytest


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


async def test_healthz(client: httpx.AsyncClient):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["mode"] == "standalone"
    assert "graph_stats" in data


# ---------------------------------------------------------------------------
# Graph endpoints
# ---------------------------------------------------------------------------


async def test_graph_nodes_returns_seed_topology(client: httpx.AsyncClient):
    """Graph nodes endpoint returns seed topology with entities and edges."""
    resp = await client.get("/graph/nodes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["entities"]) >= 10, "Seed topology should have 10+ nodes"
    assert len(data["edges"]) > 0, "Seed topology should have edges"

    # Validate entity structure
    entity = data["entities"][0]
    assert "uuid" in entity
    assert "name" in entity
    assert "node_type" in entity


async def test_graph_search(client: httpx.AsyncClient):
    """Graph search returns matching nodes."""
    resp = await client.post("/graph/search", json={"query": "quantum"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["entities"]) > 0


async def test_graph_expand_node(client: httpx.AsyncClient):
    """Expanding a node returns its neighbours."""
    # First get a node ID from the graph
    nodes_resp = await client.get("/graph/nodes")
    node_id = nodes_resp.json()["entities"][0]["uuid"]

    resp = await client.get(f"/graph/node/{node_id}/expand")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "nodes" in data
    assert "edges" in data


async def test_graph_expand_nonexistent_404(client: httpx.AsyncClient):
    resp = await client.get("/graph/node/nonexistent-node-xyz/expand")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Enter session
# ---------------------------------------------------------------------------


async def test_enter_creates_active_session(client: httpx.AsyncClient):
    """POST /enter returns a session with passage, choices, and path."""
    resp = await client.post("/enter", json={"query_text": "quantum mechanics"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["session_id"]
    assert data["state"] == "active"
    assert data["current_node_id"]
    assert len(data["player_path"]) == 1
    assert data["player_path"][0] == data["current_node_id"]
    assert data["narrative_passage"]
    assert isinstance(data["choice_cards"], list)
    assert len(data["choice_cards"]) > 0


async def test_enter_different_queries_may_differ(client: httpx.AsyncClient):
    """Different queries should resolve (possibly different) entry nodes."""
    resp1 = await client.post("/enter", json={"query_text": "quantum physics"})
    resp2 = await client.post("/enter", json={"query_text": "biological evolution"})
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # Sessions should be distinct
    assert resp1.json()["session_id"] != resp2.json()["session_id"]


# ---------------------------------------------------------------------------
# Hop
# ---------------------------------------------------------------------------


async def test_hop_advances_path(client: httpx.AsyncClient):
    """Hopping to a choice card destination extends the player path."""
    enter_resp = await client.post("/enter", json={"query_text": "thermodynamics"})
    data = enter_resp.json()
    session_id = data["session_id"]
    entry_node = data["current_node_id"]
    dest = data["choice_cards"][0]["destination_node_id"]

    hop_resp = await client.post("/hop", json={
        "session_id": session_id,
        "destination_node_id": dest,
    })
    assert hop_resp.status_code == 200
    hop_data = hop_resp.json()

    assert hop_data["session_id"] == session_id
    assert hop_data["current_node_id"] == dest
    assert hop_data["player_path"] == [entry_node, dest]
    assert hop_data["narrative_passage"]
    assert hop_data["state"] in ("active", "terminal")


async def test_hop_invalid_session_404(client: httpx.AsyncClient):
    resp = await client.post("/hop", json={
        "session_id": "nonexistent-session-id",
        "destination_node_id": "anything",
    })
    assert resp.status_code == 404


async def test_hop_prevents_revisiting_node(client: httpx.AsyncClient):
    """Hopping back to the entry node should be rejected (cycle prevention)."""
    enter_resp = await client.post("/enter", json={"query_text": "quantum"})
    data = enter_resp.json()
    session_id = data["session_id"]
    entry_node = data["current_node_id"]

    # Hop to a valid destination first
    dest = data["choice_cards"][0]["destination_node_id"]
    hop1 = await client.post("/hop", json={
        "session_id": session_id,
        "destination_node_id": dest,
    })
    assert hop1.status_code == 200

    # Try to hop back to entry node (should be blocked)
    hop2 = await client.post("/hop", json={
        "session_id": session_id,
        "destination_node_id": entry_node,
    })
    assert hop2.status_code == 400


# ---------------------------------------------------------------------------
# Session read
# ---------------------------------------------------------------------------


async def test_session_read_after_enter(client: httpx.AsyncClient):
    """GET /session/{id} returns consistent state after enter."""
    enter_resp = await client.post("/enter", json={"query_text": "epistemology"})
    data = enter_resp.json()
    session_id = data["session_id"]

    sess_resp = await client.get(f"/session/{session_id}")
    assert sess_resp.status_code == 200
    sess = sess_resp.json()
    assert sess["session_id"] == session_id
    assert sess["state"] == "active"
    assert sess["current_node_id"] == data["current_node_id"]
    assert sess["player_path"] == data["player_path"]


async def test_session_nonexistent_404(client: httpx.AsyncClient):
    resp = await client.get("/session/does-not-exist")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Multi-hop journey
# ---------------------------------------------------------------------------


async def test_multi_hop_journey(client: httpx.AsyncClient):
    """Three consecutive hops — path grows, no errors."""
    enter_resp = await client.post("/enter", json={"query_text": "consciousness"})
    assert enter_resp.status_code == 200
    data = enter_resp.json()
    session_id = data["session_id"]
    path = list(data["player_path"])
    cards = data["choice_cards"]

    for i in range(min(3, len(cards) + 2)):
        if not cards:
            break  # terminal — no more choices
        dest = cards[0]["destination_node_id"]
        hop_resp = await client.post("/hop", json={
            "session_id": session_id,
            "destination_node_id": dest,
        })
        assert hop_resp.status_code == 200, f"Hop {i+1} failed: {hop_resp.text}"
        hop_data = hop_resp.json()
        path.append(dest)
        assert hop_data["player_path"] == path
        cards = hop_data.get("choice_cards", [])

    # Path should have grown
    assert len(path) >= 2, "Expected at least 2 nodes in path after hops"
    # All nodes in path should be unique (no cycles)
    assert len(path) == len(set(path)), "Path contains duplicate nodes"
