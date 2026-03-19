"""Synapse protocol definitions for Bittensor Knowledge Network.

This file defines the wire protocol. Two bt.Synapse subclasses are transmitted
over Bittensor's axon/dendrite transport: KnowledgeQuery and NarrativeHop.
WeightCommit is an internal validator dataclass — never transmitted.

Design constraints:
- Request fields with no default are required; all response fields are Optional.
- All embedding vectors are flat list[float] (JSON-serialisable). No numpy on the wire.
- This file must stay free of business logic.
- Constants are sourced from subnet config, not hardcoded.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass, field

import bittensor as bt
from pydantic import BaseModel

from subnet import SPEC_VERSION

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
NodeID = str
SessionID = str
ChunkHash = str
EmbeddingVec = list[float]

EMBEDDING_DIM = 768
MIN_CHOICE_CARDS = 2
MAX_CHOICE_CARDS = 4


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
class KnowledgeQuery(bt.Synapse):
    """Gateway/Validator -> Domain Miners.

    Used for entry-point resolution, chunk retrieval during hops,
    and corpus integrity challenges (query_text == '__corpus_challenge__').
    """

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
class NarrativeHop(bt.Synapse):
    """Gateway -> Narrative Miners.

    Core game-loop synapse. Fired each time a traverser selects a choice card.
    All registered miners at the destination node receive the request;
    all valid responses are scored. The highest scorer wins the session step.
    """

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
# Internal: WeightCommit (not a synapse)
# ---------------------------------------------------------------------------
@dataclass
class WeightCommit:
    """Internal validator structure for accumulating and committing weights.

    Never transmitted over the network. Each validator independently calls
    set_weights() after scoring — Yuma Consensus handles aggregation.
    """

    epoch: int
    validator_uid: int
    miner_scores: dict[int, float] = field(default_factory=dict)
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
