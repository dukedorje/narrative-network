"""FastAPI gateway for the Narrative Network traversal service."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

# Load .env before any os.environ reads (OPENROUTER_API_KEY, AXON_* config, etc.)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import bittensor as bt
import numpy as np
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

log = logging.getLogger(__name__)


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

class _LocalMinerPool:
    """In-process corpus retrieval for local/dev mode.

    Loads seed corpora, embeds chunks, and serves retrieval requests
    without requiring a running domain miner.
    """

    def __init__(
        self,
        corpus_map: dict[str, list[Path]],
        embedder: Embedder,
        graph_store: GraphStore,
    ) -> None:
        self._embedder = embedder
        self._graph_store = graph_store
        # node_id -> list of {id, text, embedding}
        self._node_chunks: dict[str, list[dict]] = {}
        # node_id -> centroid embedding
        self._centroids: dict[str, np.ndarray] = {}

        self._load_corpora(corpus_map)

    def _load_corpora(self, corpus_map: dict[str, list[Path]]) -> None:
        for node_id, corpus_files in corpus_map.items():
            chunks: list[dict] = []
            texts: list[str] = []
            for fpath in corpus_files:
                if fpath.exists():
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                    # Simple chunking: ~200 words per chunk
                    words = content.split()
                    for i in range(0, len(words), 160):
                        chunk_text = " ".join(words[i : i + 200])
                        if chunk_text.strip():
                            chunks.append({"id": f"{node_id}:{len(chunks)}", "text": chunk_text})
                            texts.append(chunk_text)
            if texts:
                embeddings = self._embedder.embed(texts)
                for chunk, emb in zip(chunks, embeddings):
                    chunk["embedding"] = np.array(emb, dtype=np.float32)
                centroid = np.mean(
                    [c["embedding"] for c in chunks], axis=0
                )
                norm = np.linalg.norm(centroid)
                if norm > 0:
                    centroid = centroid / norm
                self._centroids[node_id] = centroid
            self._node_chunks[node_id] = chunks
        log.info(
            "LocalMinerPool: loaded %d nodes, %d total chunks",
            len(self._node_chunks),
            sum(len(c) for c in self._node_chunks.values()),
        )

    def rank_entry_nodes(
        self, query_embedding: list[float], top_k: int = 3
    ) -> list[tuple[str, float]]:
        """Rank nodes by cosine similarity between query and corpus centroid."""
        q = np.array(query_embedding, dtype=np.float32)
        scores: list[tuple[str, float]] = []
        for node_id, centroid in self._centroids.items():
            node = self._graph_store.get_node(node_id)
            if node and node.state == "Live":
                sim = float(centroid @ q)
                scores.append((node_id, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def retrieve_chunks(
        self, node_id: str, query_embedding: list[float], top_k: int = 5
    ) -> list[dict]:
        """Return top-k chunks from node's corpus by cosine similarity."""
        chunks = self._node_chunks.get(node_id, [])
        if not chunks:
            return []
        q = np.array(query_embedding, dtype=np.float32)
        scored = []
        for chunk in chunks:
            emb = chunk.get("embedding")
            if emb is not None:
                sim = float(emb @ q)
                scored.append((sim, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"id": c["id"], "text": c["text"], "score": s}
            for s, c in scored[:top_k]
        ]


class _LocalNarrator:
    """In-process narrative generation via OpenRouter for local/dev mode."""

    def __init__(self) -> None:
        self._client = None
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        from subnet.config import (
            NARRATIVE_MAX_TOKENS,
            NARRATIVE_MODEL,
            NARRATIVE_TEMPERATURE,
            OPENROUTER_BASE_URL,
        )

        self._model = NARRATIVE_MODEL
        self._max_tokens = NARRATIVE_MAX_TOKENS
        self._temperature = NARRATIVE_TEMPERATURE
        self._base_url = OPENROUTER_BASE_URL

        if not self._api_key:
            log.warning(
                "OPENROUTER_API_KEY not set — narrative generation will return placeholders"
            )

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
        adjacent_nodes: list[str] | None = None,
    ) -> dict:
        """Generate a narrative hop passage via OpenRouter LLM."""
        from domain.narrative.prompt import build_prompt

        system_prompt, user_prompt = build_prompt(
            destination_node_id=destination_node_id,
            player_path=player_path,
            prior_narrative=prior_narrative,
            retrieved_chunks=retrieved_chunks,
            persona="neutral",
            num_choices=min(3, len(adjacent_nodes)) if adjacent_nodes else 3,
        )

        # Append adjacent node info so the LLM knows valid destinations
        if adjacent_nodes:
            user_prompt += (
                "\n\n## Available destination nodes for choice cards\n"
                + "\n".join(f"- {nid}" for nid in adjacent_nodes)
                + "\n\nIMPORTANT: Each choice card's destination_node_id MUST be "
                "one of the nodes listed above."
            )

        if not self._api_key:
            # Fallback: return a basic template if no API key
            return self._placeholder(destination_node_id, adjacent_nodes or [])

        client = self._get_client()
        try:
            log.info("Narrator: calling model=%s max_tokens=%d for node %s", self._model, self._max_tokens, destination_node_id)
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
            if not raw:
                log.warning("Narrator: model %s returned empty content (finish_reason=%s, routed_model=%s)",
                            self._model, response.choices[0].finish_reason, getattr(response, 'model', 'unknown'))
                return self._placeholder(destination_node_id, adjacent_nodes or [])
            result = json.loads(raw)
            log.info("LLM generated passage for %s (%d chars, model=%s)", destination_node_id,
                     len(result.get("narrative_passage", "")), getattr(response, 'model', self._model))
            return result
        except json.JSONDecodeError as exc:
            log.warning("Narrator: JSON parse error: %s (raw=%r)", exc, raw[:200] if raw else "empty")
            return self._placeholder(destination_node_id, adjacent_nodes or [])
        except Exception as exc:
            log.error("Narrator: generation error: %s", exc)
            return self._placeholder(destination_node_id, adjacent_nodes or [])

    def _placeholder(self, node_id: str, adjacent: list[str]) -> dict:
        """Fallback when OpenRouter is unavailable."""
        cards = [
            {
                "text": f"Explore {nid.replace('-', ' ')}",
                "destination_node_id": nid,
                "edge_weight_delta": 0.0,
                "thematic_color": "#6ee7b7",
            }
            for nid in adjacent[:3]
        ]
        return {
            "narrative_passage": (
                f"(No OPENROUTER_API_KEY configured — set it to enable LLM narrative generation.) "
                f"You are at {node_id.replace('-', ' ').title()}."
            ),
            "choice_cards": cards,
            "knowledge_synthesis": "",
        }


def _validate_choice_cards(raw_cards: list[dict], valid_nodes: list[str]) -> list[dict]:
    """Filter and normalize choice cards, keeping only those pointing to valid adjacent nodes."""
    valid_set = set(valid_nodes)
    validated: list[dict] = []
    for card in raw_cards:
        if not isinstance(card, dict):
            continue
        dest = card.get("destination_node_id", "")
        if dest in valid_set:
            validated.append({
                "text": card.get("text", f"Explore {dest}"),
                "destination_node_id": dest,
                "edge_weight_delta": float(card.get("edge_weight_delta", 0.0)),
                "thematic_color": card.get("thematic_color", "#888888"),
            })
    # If LLM returned no valid cards, generate defaults from adjacent nodes
    if not validated:
        for nid in valid_nodes[:3]:
            validated.append({
                "text": f"Explore {nid.replace('-', ' ')}",
                "destination_node_id": nid,
                "edge_weight_delta": 0.0,
                "thematic_color": "#6ee7b7",
            })
    return validated


def create_dev_app() -> FastAPI:
    """Create a standalone gateway for local dev (no Bittensor connection)."""
    from seed.loader import load_topology

    graph_store = GraphStore(db_path=None)  # in-memory only
    _, corpus_map = load_topology(graph_store=graph_store)
    embedder = Embedder()
    safety_guard = PathSafetyGuard()

    miner_pool = _LocalMinerPool(corpus_map, embedder, graph_store)
    narrator = _LocalNarrator()

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


if os.environ.get("AXON_NETWORK") == "local":
    # Standalone dev mode — no Bittensor wallet/subtensor needed
    app = create_dev_app()
else:
    # Production: app must be created via main() with Bittensor deps
    app = None  # type: ignore[assignment]


def main() -> None:
    import uvicorn

    network = os.environ.get("AXON_NETWORK", "finney")
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
        router = Router(graph_store=graph_store, metagraph=metagraph)
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
