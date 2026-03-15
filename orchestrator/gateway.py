"""FastAPI gateway for the Narrative Network traversal service."""

from __future__ import annotations

import asyncio
from typing import Any

import bittensor as bt
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from subnet import NETUID
from subnet.graph_store import GraphStore
from subnet.protocol import NodeID, SessionID

from orchestrator.embedder import Embedder
from orchestrator.router import Router
from orchestrator.safety_guard import PathSafetyGuard
from orchestrator.session import OrchestratorSession, SessionState


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

    # In-memory session registry: session_id -> OrchestratorSession
    _sessions: dict[SessionID, OrchestratorSession] = {}

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
# Standalone / dev app instance — full local gateway with in-process miners
# ---------------------------------------------------------------------------


class _LocalMinerPool:
    """In-process miner pool: loads corpus per node, does chunk retrieval via numpy."""

    def __init__(self, corpus_map: dict[str, list], embedder: Embedder) -> None:
        from domain.corpus import CorpusLoader, Chunk

        self._chunks: dict[str, list[Chunk]] = {}
        self._centroids: dict[str, list[float]] = {}
        self._embedder = embedder

        for node_id, file_paths in corpus_map.items():
            if not file_paths:
                continue
            # Use the first file's parent as corpus_dir
            corpus_dir = file_paths[0].parent
            if not corpus_dir.exists():
                continue
            cache_path = corpus_dir.parent / ".cache" / f"{node_id}.pkl"
            loader = CorpusLoader(
                corpus_dir=str(corpus_dir),
                cache_path=str(cache_path),
            )
            chunks = loader.load()
            if chunks:
                self._chunks[node_id] = chunks
                self._centroids[node_id] = loader.centroid

    def retrieve_chunks(
        self, node_id: str, query_embedding: list[float], top_k: int = 5
    ) -> list[dict]:
        """Retrieve top-k chunks from a specific node's corpus."""
        import numpy as np

        chunks = self._chunks.get(node_id, [])
        if not chunks:
            return []

        query_emb = np.array(query_embedding, dtype=np.float32)
        chunk_embs = np.array([c.embedding for c in chunks], dtype=np.float32)
        scores = chunk_embs @ query_emb
        k = min(top_k, len(chunks))
        top_indices = np.argpartition(scores, -k)[-k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        return [
            {
                "id": chunks[i].id,
                "text": chunks[i].text,
                "hash": chunks[i].hash,
                "score": float(scores[i]),
            }
            for i in top_indices
        ]

    def rank_entry_nodes(
        self, query_embedding: list[float], top_k: int = 3
    ) -> list[tuple[str, float]]:
        """Rank all nodes by centroid similarity to query. Returns [(node_id, similarity)]."""
        import numpy as np

        query_emb = np.array(query_embedding, dtype=np.float32)
        scored: list[tuple[str, float]] = []
        for node_id, centroid in self._centroids.items():
            centroid_vec = np.array(centroid, dtype=np.float32)
            sim = float(centroid_vec @ query_emb)
            scored.append((node_id, sim))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:top_k]

    @property
    def loaded_nodes(self) -> list[str]:
        return list(self._chunks.keys())


class _LocalNarrativeGenerator:
    """Calls OpenRouter directly for narrative hop generation."""

    def __init__(self) -> None:
        from subnet.config import (
            NARRATIVE_MAX_TOKENS,
            NARRATIVE_MODEL,
            NARRATIVE_TEMPERATURE,
            OPENROUTER_BASE_URL,
        )
        import os

        self._model = NARRATIVE_MODEL
        self._max_tokens = NARRATIVE_MAX_TOKENS
        self._temperature = NARRATIVE_TEMPERATURE
        self._base_url = OPENROUTER_BASE_URL
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self._api_key or "sk-placeholder",
                base_url=self._base_url,
            )
        return self._client

    async def generate_hop(
        self,
        destination_node_id: str,
        player_path: list[str],
        prior_narrative: str,
        retrieved_chunks: list[dict],
        adjacent_nodes: list[str],
        persona: str = "explorer",
    ) -> dict[str, Any]:
        """Generate a narrative hop passage via OpenRouter. Returns parsed result dict."""
        import json
        from domain.narrative.prompt import build_prompt

        system_prompt, user_prompt = build_prompt(
            destination_node_id=destination_node_id,
            player_path=player_path,
            prior_narrative=prior_narrative,
            retrieved_chunks=retrieved_chunks,
            persona=persona,
            num_choices=min(3, max(1, len(adjacent_nodes))),
        )

        # Inject adjacent node IDs so the LLM can generate valid choice cards
        user_prompt += (
            f"\n\nAvailable destination nodes for choice cards: {adjacent_nodes}\n"
            "You MUST use only these node IDs in your choice_cards destination_node_id fields."
        )

        client = self._get_client()
        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            return json.loads(raw)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("Narrative generation failed: %s", exc)
            return {
                "narrative_passage": f"(generation failed: {exc})",
                "choice_cards": [
                    {"text": f"Continue to {n}", "destination_node_id": n,
                     "edge_weight_delta": 0.0, "thematic_color": "#888888"}
                    for n in adjacent_nodes[:3]
                ],
                "knowledge_synthesis": "",
            }


def create_dev_app() -> FastAPI:
    """Create a standalone gateway for local dev — full traversal, no Bittensor."""
    import logging

    log = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

    log.info("Loading seed topology...")
    from seed.loader import load_topology

    graph_store, corpus_map = load_topology()

    log.info("Loading embedder + corpus (this may take a moment on first run)...")
    embedder = Embedder()
    miner_pool = _LocalMinerPool(corpus_map, embedder)
    narrator = _LocalNarrativeGenerator()
    safety_guard = PathSafetyGuard()

    log.info(
        "Dev gateway ready: %d graph nodes, %d with loaded corpus",
        graph_store.stats()["node_count"],
        len(miner_pool.loaded_nodes),
    )

    app = FastAPI(title="Narrative Network Gateway (dev)", version="0.1.0-dev")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _sessions: dict[SessionID, dict[str, Any]] = {}

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": "dev",
            "netuid": NETUID,
            "graph_stats": graph_store.stats(),
            "loaded_corpus_nodes": miner_pool.loaded_nodes,
        }

    @app.get("/graph/stats")
    async def graph_stats() -> dict:
        return graph_store.stats()

    @app.get("/graph/nodes")
    async def graph_nodes() -> list[dict]:
        node_ids = graph_store.get_live_node_ids()
        return [
            {
                "node_id": nid,
                "has_corpus": nid in miner_pool.loaded_nodes,
                "neighbours": graph_store.neighbours(nid),
            }
            for nid in node_ids
        ]

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

        choice_cards = _validate_choice_cards(result.get("choice_cards", []), adjacent)

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


def _validate_choice_cards(raw_cards: list, valid_nodes: list[str]) -> list[dict]:
    """Filter and normalise choice cards to only reference valid adjacent nodes."""
    valid_set = set(valid_nodes)
    cards: list[dict] = []
    for card in raw_cards:
        if not isinstance(card, dict):
            continue
        dest = card.get("destination_node_id", "")
        if dest in valid_set:
            cards.append({
                "text": card.get("text", f"Go to {dest}"),
                "destination_node_id": dest,
                "edge_weight_delta": float(card.get("edge_weight_delta", 0.0)),
                "thematic_color": card.get("thematic_color", "#888888"),
            })
    # If LLM hallucinated bad node IDs, provide fallback cards
    if not cards and valid_nodes:
        for node_id in valid_nodes[:3]:
            cards.append({
                "text": f"Travel to {node_id}",
                "destination_node_id": node_id,
                "edge_weight_delta": 0.0,
                "thematic_color": "#888888",
            })
    return cards


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
