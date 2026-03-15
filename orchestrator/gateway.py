"""FastAPI gateway for the Narrative Network traversal service."""

from __future__ import annotations

import asyncio
from typing import Any

import bittensor as bt
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from subnet import NETUID
from subnet.graph_store import Edge, GraphStore, Node
from subnet.protocol import NodeID, SessionID

from orchestrator.arbiter import TraversalArbiter
from orchestrator.embedder import Embedder
from orchestrator.router import Router
from orchestrator.safety_guard import PathSafetyGuard
from orchestrator.session import OrchestratorSession, SessionState


# ---------------------------------------------------------------------------
# Graph browsing helpers
# ---------------------------------------------------------------------------


def _node_to_dict(node: Node) -> dict:
    return {
        "uuid": node.node_id,
        "name": node.node_id.replace("-", " ").title(),
        "node_type": "domain",
        "labels": [node.metadata.get("persona", "neutral")],
        "summary": node.metadata.get("description", ""),
        "created_at": node.created_at,
    }


def _edge_to_dict(edge: Edge) -> dict:
    return {
        "uuid": f"{edge.source_id}:{edge.dest_id}",
        "edge_type": "connects",
        "source_node_uuid": edge.source_id,
        "target_node_uuid": edge.dest_id,
        "fact": None,
        "weight": edge.weight,
    }


def _episodes_from_sessions(sessions: list[dict]) -> list[dict]:
    return [
        {
            "uuid": r["session_id"],
            "name": f"{r['source_id']} → {r['dest_id']}",
            "content": {"content": f"Traversal from {r['source_id']} to {r['dest_id']}"},
            "created_at": r["timestamp"],
        }
        for r in sessions
    ]


class _SearchRequest(BaseModel):
    query: str
    num_results: int = 20


def _register_graph_endpoints(app: FastAPI, graph_store: GraphStore) -> None:
    """Register read-only graph browsing endpoints on *app*."""

    @app.get("/graph/nodes")
    async def graph_nodes_all() -> dict:
        nodes = [n for n in graph_store.get_all_nodes() if n.state == "Live"]
        edges = graph_store.get_all_edges()
        return {
            "success": True,
            "entities": [_node_to_dict(n) for n in nodes],
            "edges": [_edge_to_dict(e) for e in edges],
            "episodes": _episodes_from_sessions(graph_store.sample_recent_sessions(10)),
            "num_results": len(nodes),
        }

    @app.post("/graph/search")
    async def graph_search(req: _SearchRequest) -> dict:
        q = req.query.lower()
        all_live = [n for n in graph_store.get_all_nodes() if n.state == "Live"]
        words = q.split()
        matched = [
            n for n in all_live
            if q in n.node_id.lower()
            or any(w in n.metadata.get("description", "").lower() for w in words)
        ] or all_live
        matched = matched[: req.num_results]
        matched_ids = {n.node_id for n in matched}
        edges = [
            _edge_to_dict(e)
            for e in graph_store.get_all_edges()
            if e.source_id in matched_ids or e.dest_id in matched_ids
        ]
        return {
            "success": True,
            "entities": [_node_to_dict(n) for n in matched],
            "edges": edges,
            "episodes": _episodes_from_sessions(graph_store.sample_recent_sessions(5)),
            "num_results": len(matched),
        }

    @app.get("/graph/node/{node_id}/expand")
    async def graph_expand_node(node_id: str) -> dict:
        node = graph_store.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
        neighbour_ids = set(graph_store.neighbours(node_id))
        neighbour_nodes = [
            graph_store.get_node(nid) for nid in neighbour_ids if graph_store.get_node(nid)
        ]
        edges = [
            _edge_to_dict(e)
            for e in graph_store.get_all_edges()
            if (e.source_id == node_id and e.dest_id in neighbour_ids)
            or (e.dest_id == node_id)
        ]
        return {
            "success": True,
            "nodes": [_node_to_dict(n) for n in neighbour_nodes if n is not None],
            "edges": edges,
            "num_results": len(neighbour_nodes),
        }


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class EnterRequest(BaseModel):
    query_text: str
    top_k_entry: int = 3


class EnterResponse(BaseModel):
    session_id: SessionID
    current_node_id: NodeID | None
    narrative_passage: str | None
    choice_cards: list[dict] | None
    knowledge_synthesis: str | None
    player_path: list[NodeID]
    state: str


class HopRequest(BaseModel):
    session_id: SessionID
    destination_node_id: NodeID


class HopResponse(BaseModel):
    session_id: SessionID
    current_node_id: NodeID | None
    narrative_passage: str | None
    choice_cards: list[dict] | None
    knowledge_synthesis: str | None
    player_path: list[NodeID]
    state: str
    error: str | None = None


class SessionResponse(BaseModel):
    session_id: SessionID
    state: str
    current_node_id: NodeID | None
    player_path: list[NodeID]
    choice_cards: list[dict] | None
    created_at: float
    updated_at: float


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    graph_store: GraphStore,
    embedder: Embedder,
    router: Router,
    safety_guard: PathSafetyGuard,
    wallet: bt.Wallet,
    subtensor: bt.Subtensor,
    metagraph: bt.metagraph,
) -> FastAPI:
    """Create and return the configured FastAPI application."""

    app = FastAPI(title="Narrative Network Gateway", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_graph_endpoints(app, graph_store)

    # In-memory session registry: session_id -> OrchestratorSession
    _sessions: dict[SessionID, OrchestratorSession] = {}
    _arbiter = TraversalArbiter()

    dendrite = bt.Dendrite(wallet=wallet)

    # ------------------------------------------------------------------
    # POST /enter
    # ------------------------------------------------------------------

    @app.post("/enter", response_model=EnterResponse)
    async def enter(req: EnterRequest) -> EnterResponse:
        query_embedding = embedder.embed_one(req.query_text)

        # Broadcast KnowledgeQuery to all domain miners to find entry nodes
        from subnet.protocol import KnowledgeQuery

        active_axons = [
            axon
            for axon in metagraph.axons
            if axon.ip != "0.0.0.0" and axon.port != 0
        ]
        if not active_axons:
            raise HTTPException(status_code=503, detail="No active miners available")

        synapse = KnowledgeQuery(
            query_embedding=query_embedding,
            query_text=req.query_text,
            top_k=req.top_k_entry,
            session_id="",
        )
        responses: list[KnowledgeQuery] = await dendrite(
            axons=active_axons,
            synapse=synapse,
            deserialize=False,
        )
        valid_responses = [r for r in responses if r.node_id is not None]

        ranked_nodes = router.rank_entry_nodes(
            query_embedding=query_embedding,
            responses=valid_responses,
            top_k=req.top_k_entry,
        )
        if not ranked_nodes:
            # TODO: unbrowse_fallback_enter — if no ranked_nodes, use UnbrowseClient.fetch_context
            # to synthesize entry context and return a virtual node response
            raise HTTPException(status_code=503, detail="No entry nodes resolved")

        entry_node_id = ranked_nodes[0]
        axon = router.resolve_narrative_miner(entry_node_id)
        if axon is None:
            raise HTTPException(
                status_code=503, detail=f"No miner found for node {entry_node_id}"
            )

        session = OrchestratorSession(
            dendrite=dendrite,
            metagraph=metagraph,
            safety_guard=safety_guard,
        )
        _sessions[session.session_id] = session

        result = await session.enter(
            query_text=req.query_text,
            query_embedding=query_embedding,
            entry_node_id=entry_node_id,
            axon=axon,
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return EnterResponse(
            session_id=result["session_id"],
            current_node_id=result.get("current_node_id"),
            narrative_passage=result.get("narrative_passage"),
            choice_cards=result.get("choice_cards"),
            knowledge_synthesis=result.get("knowledge_synthesis"),
            player_path=result.get("player_path", []),
            state=result.get("state", SessionState.ACTIVE.value),
        )

    # ------------------------------------------------------------------
    # POST /hop
    # ------------------------------------------------------------------

    @app.post("/hop", response_model=HopResponse)
    async def hop(req: HopRequest) -> HopResponse:
        session = _sessions.get(req.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.state != SessionState.ACTIVE:
            raise HTTPException(
                status_code=409, detail=f"Session is {session.state.value}"
            )

        axon = router.resolve_narrative_miner(req.destination_node_id)
        if axon is None:
            raise HTTPException(
                status_code=503,
                detail=f"No miner found for node {req.destination_node_id}",
            )

        result = await session.hop(
            destination_node_id=req.destination_node_id,
            axon=axon,
        )

        # Run Arkhai arbiter to filter the next-hop candidate set
        raw_cards: list[dict] = result.get("choice_cards") or []
        if raw_cards:
            candidates = [c["destination_node_id"] for c in raw_cards]
            node_descriptions = {
                nid: (graph_store.get_node(nid).metadata.get("description", nid)
                      if graph_store.get_node(nid) else nid)
                for nid in candidates + [req.destination_node_id]
            }
            arbiter_result = await _arbiter.check_hop(
                session_id=req.session_id,
                source_node=session.player_path[-2] if len(session.player_path) > 1 else req.destination_node_id,
                dest_node=req.destination_node_id,
                player_path=list(session.player_path),
                candidates=candidates,
                node_descriptions=node_descriptions,
            )
            approved_ids = set(arbiter_result.filtered_candidates)
            filtered_cards = [c for c in raw_cards if c["destination_node_id"] in approved_ids]
            result["choice_cards"] = filtered_cards or raw_cards  # never return empty if fallback
            if arbiter_result.reasoning and not result.get("knowledge_synthesis"):
                result["knowledge_synthesis"] = arbiter_result.reasoning

        return HopResponse(
            session_id=result["session_id"],
            current_node_id=result.get("current_node_id"),
            narrative_passage=result.get("narrative_passage"),
            choice_cards=result.get("choice_cards"),
            knowledge_synthesis=result.get("knowledge_synthesis"),
            player_path=result.get("player_path", []),
            state=result.get("state", session.state.value),
            error=result.get("error"),
        )

    # ------------------------------------------------------------------
    # GET /session/{id}
    # ------------------------------------------------------------------

    @app.get("/session/{session_id}", response_model=SessionResponse)
    async def get_session(session_id: SessionID) -> SessionResponse:
        session = _sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        data = session.to_dict()
        return SessionResponse(**data)

    # ------------------------------------------------------------------
    # WS /session/{id}/live
    # ------------------------------------------------------------------

    @app.websocket("/session/{session_id}/live")
    async def session_live(websocket: WebSocket, session_id: SessionID) -> None:
        """Push session state updates to the client over WebSocket.

        The client can send JSON: {"destination_node_id": "<id>"} to trigger hops.
        The server pushes HopResponse-shaped JSON after each hop or state change.
        """
        session = _sessions.get(session_id)
        if session is None:
            await websocket.close(code=4004)
            return

        await websocket.accept()
        try:
            # Send current state immediately on connect
            await websocket.send_json(session.to_dict())

            while session.state == SessionState.ACTIVE:
                try:
                    data: dict[str, Any] = await asyncio.wait_for(
                        websocket.receive_json(), timeout=60.0
                    )
                except asyncio.TimeoutError:
                    # Send a keepalive ping
                    await websocket.send_json({"type": "ping"})
                    continue

                dest_node = data.get("destination_node_id")
                if not dest_node:
                    await websocket.send_json({"error": "destination_node_id required"})
                    continue

                axon = router.resolve_narrative_miner(dest_node)
                if axon is None:
                    await websocket.send_json({"error": f"No miner for node {dest_node}"})
                    continue

                result = await session.hop(destination_node_id=dest_node, axon=axon)
                await websocket.send_json(result)

            # Final state push on terminal/error
            await websocket.send_json(session.to_dict())

        except WebSocketDisconnect:
            pass

    # ------------------------------------------------------------------
    # GET /healthz
    # ------------------------------------------------------------------

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "netuid": NETUID,
            "active_sessions": len(
                [s for s in _sessions.values() if s.state == SessionState.ACTIVE]
            ),
            "total_sessions": len(_sessions),
        }

    return app


# ---------------------------------------------------------------------------
# Standalone / dev app instance
# ---------------------------------------------------------------------------

def create_dev_app() -> FastAPI:
    """Create a standalone gateway for local dev (no Bittensor connection)."""
    from seed.loader import load_topology

    graph_store = GraphStore(db_path=None)  # in-memory only
    load_topology(graph_store=graph_store)
    embedder = Embedder()
    safety_guard = PathSafetyGuard()

    app = FastAPI(title="Narrative Network Gateway (dev)", version="0.1.0-dev")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _sessions: dict[SessionID, dict[str, Any]] = {}
    _arbiter = TraversalArbiter()

    _register_graph_endpoints(app, graph_store)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": "standalone",
            "netuid": NETUID,
            "graph_stats": graph_store.stats(),
        }

    @app.get("/graph/stats")
    async def graph_stats() -> dict:
        return graph_store.stats()

    @app.post("/enter", response_model=EnterResponse)
    async def enter(req: EnterRequest) -> dict[str, Any]:
        # Embed the query
        query_embedding = embedder.embed_one(req.query_text)

        # Rank entry nodes by centroid similarity
        ranked = miner_pool.rank_entry_nodes(query_embedding, top_k=req.top_k_entry)
        if not ranked:
            raise HTTPException(status_code=503, detail="No nodes with loaded corpus")

        entry_node_id, similarity = ranked[0]

        # Retrieve chunks from entry node
        chunks = miner_pool.retrieve_chunks(entry_node_id, query_embedding, top_k=5)

        # Get adjacent nodes for choice cards
        adjacent = safety_guard.filter_candidates(
            graph_store.neighbours(entry_node_id), [entry_node_id]
        )

        # Generate opening narrative
        result = await narrator.generate_hop(
            destination_node_id=entry_node_id,
            player_path=[],
            prior_narrative="",
            retrieved_chunks=chunks,
            adjacent_nodes=adjacent,
        )

        # Build choice cards from LLM response, filtering to valid adjacent nodes
        choice_cards = _validate_choice_cards(result.get("choice_cards", []), adjacent)

        import uuid

        session_id = str(uuid.uuid4())
        _sessions[session_id] = {
            "session_id": session_id,
            "state": "active",
            "current_node_id": entry_node_id,
            "player_path": [entry_node_id],
            "prior_narrative": result.get("narrative_passage", ""),
            "query_embedding": query_embedding,
        }

        return {
            "session_id": session_id,
            "current_node_id": entry_node_id,
            "narrative_passage": result.get("narrative_passage"),
            "choice_cards": choice_cards,
            "knowledge_synthesis": result.get("knowledge_synthesis"),
            "player_path": [entry_node_id],
            "state": "active",
        }

    @app.post("/hop", response_model=HopResponse)
    async def hop(req: HopRequest) -> dict[str, Any]:
        session = _sessions.get(req.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if session["state"] != "active":
            raise HTTPException(status_code=400, detail=f"Session is {session['state']}")

        player_path = session["player_path"]

        # Safety checks
        ok, reason = safety_guard.check_path_length(player_path)
        if not ok:
            session["state"] = "terminal"
            raise HTTPException(status_code=400, detail=reason)

        safe = safety_guard.filter_candidates([req.destination_node_id], player_path)
        if not safe:
            raise HTTPException(
                status_code=400,
                detail=f"Node {req.destination_node_id} already visited or blocked",
            )

        # Retrieve chunks from destination node
        query_embedding = session["query_embedding"]
        chunks = miner_pool.retrieve_chunks(req.destination_node_id, query_embedding, top_k=5)

        # Get adjacent nodes (excluding already visited)
        new_path = player_path + [req.destination_node_id]
        adjacent = safety_guard.filter_candidates(
            graph_store.neighbours(req.destination_node_id), new_path
        )

        # Check for terminal state (no adjacent nodes left)
        if not adjacent:
            session["state"] = "terminal"

        # Generate narrative hop
        result = await narrator.generate_hop(
            destination_node_id=req.destination_node_id,
            player_path=player_path,
            prior_narrative=session["prior_narrative"],
            retrieved_chunks=chunks,
            adjacent_nodes=adjacent if adjacent else ["(terminal)"],
        )

        raw_cards = _validate_choice_cards(result.get("choice_cards", []), adjacent)

        # Arkhai arbiter filters candidates to meaningful forward steps
        if raw_cards:
            node_descriptions = {
                nid: (graph_store.get_node(nid).metadata.get("description", nid)
                      if graph_store.get_node(nid) else nid)
                for nid in adjacent + [req.destination_node_id]
            }
            arbiter_result = await _arbiter.check_hop(
                session_id=req.session_id,
                source_node=player_path[-1] if player_path else req.destination_node_id,
                dest_node=req.destination_node_id,
                player_path=player_path,
                candidates=[c["destination_node_id"] for c in raw_cards],
                node_descriptions=node_descriptions,
            )
            approved = set(arbiter_result.filtered_candidates)
            choice_cards = [c for c in raw_cards if c["destination_node_id"] in approved] or raw_cards
        else:
            choice_cards = raw_cards

        # Update session
        passage = result.get("narrative_passage", "")
        session["player_path"] = new_path
        session["current_node_id"] = req.destination_node_id
        session["prior_narrative"] = (
            session["prior_narrative"] + "\n\n" + passage
        ).strip()

        if not adjacent:
            session["state"] = "terminal"

        return {
            "session_id": req.session_id,
            "current_node_id": req.destination_node_id,
            "narrative_passage": passage,
            "choice_cards": choice_cards,
            "knowledge_synthesis": result.get("knowledge_synthesis"),
            "player_path": new_path,
            "state": session["state"],
        }

    @app.get("/session/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        session = _sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "session_id": session["session_id"],
            "state": session["state"],
            "current_node_id": session["current_node_id"],
            "player_path": session["player_path"],
        }

    return app


import os as _os

if _os.environ.get("AXON_NETWORK") == "local":
    # Standalone dev mode — no Bittensor wallet/subtensor needed
    app = create_dev_app()
else:
    # Production: app must be created via main() with Bittensor deps
    app = None  # type: ignore[assignment]


def main() -> None:
    import uvicorn

    network = _os.environ.get("AXON_NETWORK", "finney")
    if network == "local":
        uvicorn.run(
            "orchestrator.gateway:app",
            host="0.0.0.0",
            port=8080,
            reload=False,
        )
    else:
        import bittensor as bt
        from subnet import NETUID as _netuid

        config = bt.Config()
        wallet = bt.Wallet(config=config)
        subtensor = bt.Subtensor(config=config)
        metagraph = subtensor.metagraph(_netuid)

        graph_store = GraphStore()
        embedder = Embedder()
        router = Router(graph_store=graph_store, embedder=embedder)
        safety_guard = PathSafetyGuard(graph_store=graph_store)

        _app = create_app(
            graph_store=graph_store,
            embedder=embedder,
            router=router,
            safety_guard=safety_guard,
            wallet=wallet,
            subtensor=subtensor,
            metagraph=metagraph,
        )
        uvicorn.run(_app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
