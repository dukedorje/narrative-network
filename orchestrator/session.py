"""OrchestratorSession — manages the traversal lifecycle for a single player session."""

from __future__ import annotations

import enum
import time
import uuid
from typing import Any

import bittensor as bt

from subnet import NETUID
from subnet.protocol import KnowledgeQuery, NarrativeHop, NodeID, SessionID

from orchestrator.safety_guard import PathSafetyGuard


class SessionState(enum.Enum):
    CREATED = "created"
    ACTIVE = "active"
    TERMINAL = "terminal"
    ERROR = "error"


class OrchestratorSession:
    """Manages one player's traversal through the knowledge graph.

    Lifecycle:
        session = OrchestratorSession(...)
        await session.enter(query_text, query_embedding)   # resolves entry node
        await session.hop(destination_node_id)             # each subsequent step
    """

    def __init__(
        self,
        session_id: SessionID | None = None,
        dendrite: bt.Dendrite | None = None,
        metagraph: bt.metagraph | None = None,
        safety_guard: PathSafetyGuard | None = None,
        top_k_chunks: int = 5,
    ):
        self.session_id: SessionID = session_id or str(uuid.uuid4())
        self.dendrite = dendrite
        self.metagraph = metagraph
        self.safety_guard = safety_guard or PathSafetyGuard()

        self.state: SessionState = SessionState.CREATED
        self.player_path: list[NodeID] = []
        self.path_embeddings: list[list[float]] = []
        self.prior_narrative: str = ""
        self.current_node_id: NodeID | None = None
        self.choice_cards: list[dict] | None = None
        self.top_k_chunks = top_k_chunks
        self.created_at: float = time.time()
        self.updated_at: float = self.created_at

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _active_axons(self) -> list[bt.AxonInfo]:
        """Return all axons in the metagraph with a valid IP/port."""
        if self.metagraph is None:
            return []
        return [
            axon
            for axon in self.metagraph.axons
            if axon.ip != "0.0.0.0" and axon.port != 0
        ]

    async def _fetch_chunks(
        self,
        query_embedding: list[float],
        query_text: str,
        axons: list[bt.AxonInfo],
    ) -> list[KnowledgeQuery]:
        """Broadcast a KnowledgeQuery to domain miners and return all responses."""
        if not axons or self.dendrite is None:
            return []

        synapse = KnowledgeQuery(
            query_embedding=query_embedding,
            query_text=query_text,
            top_k=self.top_k_chunks,
            session_id=self.session_id,
        )
        responses: list[KnowledgeQuery] = await self.dendrite(
            axons=axons,
            synapse=synapse,
            deserialize=False,
        )
        return [r for r in responses if r.chunks is not None]

    async def _generate_hop(
        self,
        destination_node_id: NodeID,
        retrieved_chunks: list[dict],
        axon: bt.AxonInfo,
    ) -> NarrativeHop | None:
        """Send a NarrativeHop synapse to the miner at destination_node_id."""
        if self.dendrite is None:
            return None

        synapse = NarrativeHop(
            destination_node_id=destination_node_id,
            player_path=list(self.player_path),
            path_embeddings=list(self.path_embeddings),
            prior_narrative=self.prior_narrative,
            retrieved_chunks=retrieved_chunks,
            session_id=self.session_id,
        )
        responses: list[NarrativeHop] = await self.dendrite(
            axons=[axon],
            synapse=synapse,
            deserialize=False,
        )
        if not responses:
            return None
        resp = responses[0]
        if resp.narrative_passage is None:
            return None
        return resp

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enter(
        self,
        query_text: str,
        query_embedding: list[float],
        entry_node_id: NodeID,
        axon: bt.AxonInfo,
    ) -> dict[str, Any]:
        """Start a session at entry_node_id.

        Fetches initial chunks and generates the opening narrative passage.
        Returns the first hop result dict.
        """
        if self.state != SessionState.CREATED:
            raise RuntimeError(f"Cannot enter: session is already {self.state.value}")

        self.state = SessionState.ACTIVE
        self.current_node_id = entry_node_id

        # Fetch domain chunks for context
        active_axons = self._active_axons()
        chunk_responses = await self._fetch_chunks(query_embedding, query_text, active_axons)
        retrieved_chunks: list[dict] = []
        for resp in chunk_responses:
            if resp.chunks:
                retrieved_chunks.extend(resp.chunks)

        # Generate opening passage
        hop_resp = await self._generate_hop(entry_node_id, retrieved_chunks, axon)
        if hop_resp is None:
            self.state = SessionState.ERROR
            return {"error": "No response from entry miner", "session_id": self.session_id}

        ok, reason = self.safety_guard.check_passage(hop_resp.narrative_passage or "")
        if not ok:
            self.state = SessionState.ERROR
            return {"error": reason, "session_id": self.session_id}

        self.player_path.append(entry_node_id)
        if hop_resp.passage_embedding:
            self.path_embeddings.append(hop_resp.passage_embedding)
        self.prior_narrative = hop_resp.narrative_passage or ""
        self.choice_cards = (
            [c.model_dump() for c in hop_resp.choice_cards] if hop_resp.choice_cards else []
        )
        self.safety_guard.tick()
        self.updated_at = time.time()

        return self._hop_result(hop_resp)

    async def hop(
        self,
        destination_node_id: NodeID,
        axon: bt.AxonInfo,
        query_embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        """Advance the session to destination_node_id.

        Returns the hop result dict or an error dict.
        """
        if self.state != SessionState.ACTIVE:
            raise RuntimeError(f"Cannot hop: session is {self.state.value}")

        # Safety checks
        ok, reason = self.safety_guard.check_path_length(self.player_path)
        if not ok:
            self.state = SessionState.TERMINAL
            return {"error": reason, "session_id": self.session_id, "terminal": True}

        safe_candidates = self.safety_guard.filter_candidates(
            [destination_node_id], self.player_path
        )
        if not safe_candidates:
            return {
                "error": f"Node {destination_node_id} already visited or blocked",
                "session_id": self.session_id,
            }

        # Fetch chunks for destination context
        retrieved_chunks: list[dict] = []
        if query_embedding is not None:
            active_axons = self._active_axons()
            chunk_responses = await self._fetch_chunks(
                query_embedding, "", active_axons
            )
            for resp in chunk_responses:
                if resp.chunks:
                    retrieved_chunks.extend(resp.chunks)

        hop_resp = await self._generate_hop(destination_node_id, retrieved_chunks, axon)
        if hop_resp is None:
            return {"error": "No response from miner", "session_id": self.session_id}

        ok, reason = self.safety_guard.check_passage(hop_resp.narrative_passage or "")
        if not ok:
            return {"error": reason, "session_id": self.session_id}

        self.player_path.append(destination_node_id)
        if hop_resp.passage_embedding:
            self.path_embeddings.append(hop_resp.passage_embedding)
        self.prior_narrative = (self.prior_narrative + "\n\n" + (hop_resp.narrative_passage or "")).strip()
        self.current_node_id = destination_node_id
        self.choice_cards = (
            [c.model_dump() for c in hop_resp.choice_cards] if hop_resp.choice_cards else []
        )
        self.safety_guard.tick()
        self.updated_at = time.time()

        return self._hop_result(hop_resp)

    def _hop_result(self, hop_resp: NarrativeHop) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "current_node_id": self.current_node_id,
            "narrative_passage": hop_resp.narrative_passage,
            "choice_cards": self.choice_cards,
            "knowledge_synthesis": hop_resp.knowledge_synthesis,
            "player_path": list(self.player_path),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialise session state for the GET /session/{id} endpoint."""
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "current_node_id": self.current_node_id,
            "player_path": list(self.player_path),
            "choice_cards": self.choice_cards,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
