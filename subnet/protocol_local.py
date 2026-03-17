"""Local-mode protocol models — no bittensor dependency.

Field-for-field mirror of subnet/protocol.py. These models are plain
Pydantic BaseModel subclasses with stub dendrite/axon/timeout fields
that downstream code accesses on Synapse objects.

This file MUST be kept in sync with protocol.py. Any field added to
KnowledgeQuery or NarrativeHop there must be added here too.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from dataclasses import field as dc_field

from pydantic import BaseModel

from subnet import SPEC_VERSION

# ---------------------------------------------------------------------------
# Type aliases (duplicated from protocol.py to avoid importing it)
# ---------------------------------------------------------------------------
NodeID = str
SessionID = str
ChunkHash = str
EmbeddingVec = list[float]

EMBEDDING_DIM = 768
MIN_CHOICE_CARDS = 2
MAX_CHOICE_CARDS = 4


# ---------------------------------------------------------------------------
# Synapse field stubs
# ---------------------------------------------------------------------------
@dataclass
class _DendriteStub:
    """Minimal stand-in for bt.TerminalInfo (dendrite endpoint)."""

    hotkey: str = ""
    ip: str = "127.0.0.1"
    port: int = 0
    status_code: int | None = None
    status_message: str | None = None


@dataclass
class _AxonStub:
    """Minimal stand-in for bt.TerminalInfo (axon endpoint)."""

    hotkey: str = ""
    ip: str = "127.0.0.1"
    port: int = 0


# ---------------------------------------------------------------------------
# Base class providing the Synapse interface contract
# ---------------------------------------------------------------------------
class _SynapseBase(BaseModel):
    """Base providing the bt.Synapse interface contract without bittensor."""

    model_config = {"arbitrary_types_allowed": True}

    # Stub fields that downstream code accesses on real Synapses
    dendrite: _DendriteStub | None = None
    axon: _AxonStub | None = None
    timeout: float | None = None
    name: str = ""
    total_size: int = 0
    header_size: int = 0
    computed_body_hash: str = ""

    def get_required_hash_fields(self) -> list[str]:
        return []

    def deserialize(self) -> dict:
        return {}

    def model_post_init(self, __context: typing.Any) -> None:
        super().model_post_init(__context)
        if not self.name:
            self.name = self.__class__.__name__
        if self.dendrite is None:
            self.dendrite = _DendriteStub()
        if self.axon is None:
            self.axon = _AxonStub()


# ---------------------------------------------------------------------------
# Inline models
# ---------------------------------------------------------------------------
class ChoiceCard(BaseModel):
    """A branch option presented to the traverser."""

    text: str
    destination_node_id: NodeID
    edge_weight_delta: float = 0.0
    thematic_color: str = "#888888"


# ---------------------------------------------------------------------------
# Synapse 1: KnowledgeQuery
# ---------------------------------------------------------------------------
class KnowledgeQuery(_SynapseBase):
    """Local-mode mirror of protocol.KnowledgeQuery."""

    # Request fields
    query_embedding: EmbeddingVec = []
    query_text: str = ""
    top_k: int = 5
    session_id: SessionID = ""
    spec_version: str = SPEC_VERSION

    # Response fields
    chunks: typing.Optional[list[dict]] = None
    domain_similarity: typing.Optional[float] = None
    node_id: typing.Optional[NodeID] = None
    agent_uid: typing.Optional[int] = None
    merkle_proof: typing.Optional[dict] = None

    def get_required_hash_fields(self) -> list[str]:
        return ["query_embedding", "query_text", "session_id"]

    def deserialize(self) -> dict:
        return {
            "chunks": self.chunks,
            "domain_similarity": self.domain_similarity,
            "node_id": self.node_id,
            "merkle_proof": self.merkle_proof,
        }


# ---------------------------------------------------------------------------
# Synapse 2: NarrativeHop
# ---------------------------------------------------------------------------
class NarrativeHop(_SynapseBase):
    """Local-mode mirror of protocol.NarrativeHop."""

    # Request fields
    destination_node_id: NodeID = ""
    player_path: list[NodeID] = []
    path_embeddings: list[EmbeddingVec] = []
    prior_narrative: str = ""
    retrieved_chunks: list[dict] = []
    session_id: SessionID = ""
    spec_version: str = SPEC_VERSION
    integration_notice: typing.Optional[str] = None

    # Response fields
    narrative_passage: typing.Optional[str] = None
    choice_cards: typing.Optional[list[ChoiceCard]] = None
    knowledge_synthesis: typing.Optional[str] = None
    passage_embedding: typing.Optional[EmbeddingVec] = None
    agent_uid: typing.Optional[int] = None

    def get_required_hash_fields(self) -> list[str]:
        return ["destination_node_id", "player_path", "session_id"]

    def deserialize(self) -> dict:
        return {
            "narrative_passage": self.narrative_passage,
            "choice_cards": [c.model_dump() for c in self.choice_cards]
            if self.choice_cards
            else None,
            "knowledge_synthesis": self.knowledge_synthesis,
            "passage_embedding": self.passage_embedding,
        }


# ---------------------------------------------------------------------------
# Internal: WeightCommit (not a synapse — plain dataclass, no bt dependency)
# ---------------------------------------------------------------------------
@dataclass
class WeightCommit:
    """Internal validator structure for accumulating and committing weights."""

    epoch: int
    validator_uid: int
    miner_scores: dict[int, float] = dc_field(default_factory=dict)
    session_count: int = 0
    mean_score: float = 0.0

    def normalise(self) -> None:
        total = sum(self.miner_scores.values())
        if total > 0:
            self.miner_scores = {
                uid: score / total for uid, score in self.miner_scores.items()
            }

    def to_arrays(self) -> tuple[list[int], list[float]]:
        uids = list(self.miner_scores.keys())
        weights = list(self.miner_scores.values())
        return uids, weights
