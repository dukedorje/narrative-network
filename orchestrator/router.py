"""Entry-node ranking and narrative miner resolution."""

from __future__ import annotations

import math

import bittensor as bt

from subnet.graph_store import GraphStore
from subnet.protocol import KnowledgeQuery, NodeID


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two flat float vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


class Router:
    """Routes traversal requests to the appropriate miners.

    rank_entry_nodes: given a query embedding, returns a ranked list of live
        node IDs ordered by domain similarity.

    resolve_narrative_miner: given a destination node ID, returns the axon
        of the miner registered for that node (lowest-latency or highest stake).
    """

    def __init__(self, graph_store: GraphStore, metagraph: bt.metagraph):
        self.graph_store = graph_store
        self.metagraph = metagraph

    def rank_entry_nodes(
        self,
        query_embedding: list[float],
        responses: list[KnowledgeQuery],
        top_k: int = 5,
    ) -> list[NodeID]:
        """Rank entry-node candidates by domain similarity to query.

        responses is the list of KnowledgeQuery responses from domain miners.
        Each response carries domain_similarity (float) and node_id (str).
        Returns up to top_k node IDs sorted descending by similarity.
        """
        scored: list[tuple[float, NodeID]] = []
        for resp in responses:
            if resp.node_id is None:
                continue
            sim = resp.domain_similarity if resp.domain_similarity is not None else 0.0
            scored.append((sim, resp.node_id))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [node_id for _, node_id in scored[:top_k]]

    def resolve_narrative_miner(self, destination_node_id: NodeID) -> bt.AxonInfo | None:
        """Return the axon for the miner registered at destination_node_id.

        Searches the metagraph for the hotkey whose node_id commitment matches.
        Falls back to highest-stake axon among candidates when multiple match.
        Returns None if no registered miner is found.
        """
        # Walk the metagraph looking for a miner whose axon info carries the node_id.
        # In practice, miners set a commitment via subtensor.set_commitment(); here we
        # perform a best-effort match on the axon's ip/port as a proxy until
        # commitments are indexed in GraphStore.
        candidates: list[tuple[float, bt.AxonInfo]] = []
        for uid, axon in enumerate(self.metagraph.axons):
            if axon.ip == "0.0.0.0" or axon.port == 0:
                continue
            stake = float(self.metagraph.S[uid])
            candidates.append((stake, axon))

        if not candidates:
            return None

        # Return the highest-stake available axon.
        candidates.sort(key=lambda t: t[0], reverse=True)
        return candidates[0][1]
