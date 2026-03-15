"""E2E smoke tests — run against any deployment.

Usage:
    E2E_BASE_URL=https://futograph.online uv run pytest tests/e2e/ -v
    E2E_BASE_URL=http://localhost:8080 uv run pytest tests/e2e/ -v
"""

import httpx


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


async def test_health(client: httpx.AsyncClient, gw_path):
    """Gateway /healthz returns ok."""
    resp = await client.get(gw_path("/healthz"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Graph data
# ---------------------------------------------------------------------------


async def test_graph_nodes(client: httpx.AsyncClient, gw_path):
    """Graph nodes endpoint returns seed topology."""
    resp = await client.get(gw_path("/graph/nodes"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["entities"]) > 0, "Expected at least one graph node"
    entity = data["entities"][0]
    assert "uuid" in entity
    assert "name" in entity


# ---------------------------------------------------------------------------
# Enter session
# ---------------------------------------------------------------------------


async def test_enter_session(client: httpx.AsyncClient, gw_path):
    """POST /enter creates a session with a narrative passage and choice cards."""
    resp = await client.post(gw_path("/enter"), json={"query_text": "quantum mechanics"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["session_id"], "Expected a session ID"
    assert data["state"] == "active"
    assert data["current_node_id"], "Expected an entry node"
    assert len(data["player_path"]) == 1
    assert data["narrative_passage"], "Expected a narrative passage"
    assert isinstance(data["choice_cards"], list)
    assert len(data["choice_cards"]) > 0, "Expected at least one choice card"

    card = data["choice_cards"][0]
    assert "destination_node_id" in card
    assert "text" in card


# ---------------------------------------------------------------------------
# Enter + Hop (full traversal)
# ---------------------------------------------------------------------------


async def test_enter_and_hop(client: httpx.AsyncClient, gw_path):
    """Full traversal: enter → pick a choice card → hop → verify path grows."""
    # Enter
    enter_resp = await client.post(gw_path("/enter"), json={"query_text": "thermodynamics"})
    assert enter_resp.status_code == 200
    enter_data = enter_resp.json()
    session_id = enter_data["session_id"]
    cards = enter_data["choice_cards"]
    assert len(cards) > 0, "Need at least one choice to hop"

    # Hop to the first choice
    dest = cards[0]["destination_node_id"]
    hop_resp = await client.post(gw_path("/hop"), json={
        "session_id": session_id,
        "destination_node_id": dest,
    })
    assert hop_resp.status_code == 200
    hop_data = hop_resp.json()

    assert hop_data["session_id"] == session_id
    assert len(hop_data["player_path"]) == 2
    assert hop_data["player_path"][1] == dest
    assert hop_data["current_node_id"] == dest
    assert hop_data["narrative_passage"], "Expected a narrative passage on hop"
