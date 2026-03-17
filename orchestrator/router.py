"""Entry-node ranking and miner resolution."""

from __future__ import annotations

import logging
import math
import threading
from typing import TYPE_CHECKING

from subnet._bt_compat import _BT_AVAILABLE

if _BT_AVAILABLE:
    import bittensor as bt
else:
    bt = None  # type: ignore

from subnet.graph_store import GraphStore

if _BT_AVAILABLE:
    from subnet.protocol import KnowledgeQuery, NodeID
else:
    from subnet.protocol_local import KnowledgeQuery, NodeID  # type: ignore

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


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

    resolve_miner: given a destination node ID, returns the axon of the miner
        registered for that node (highest stake among miners serving that node,
        falling back to highest-stake overall).

    The miner-to-node index is populated two ways:
      1. Eagerly via ``index_miner()`` / ``deindex_miner()`` — called from
         MetagraphWatcher registration callbacks with a node_id obtained from
         an on-chain commitment fetch.
      2. Lazily via ``update_from_responses()`` — called after each
         KnowledgeQuery broadcast; miners self-report their node_id in
         synapse responses so the index stays warm even without a subtensor.
    """

    def __init__(self, graph_store: GraphStore, metagraph: bt.metagraph):
        self.graph_store = graph_store
        self.metagraph = metagraph

        # node_id -> list of (stake, uid, axon) for all miners serving that node
        self._node_to_axons: dict[NodeID, list[tuple[float, int, bt.AxonInfo]]] = {}
        # uid -> node_id for reverse lookup (deindex)
        self._uid_to_node: dict[int, NodeID] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def index_miner(self, uid: int, axon: bt.AxonInfo, node_id: NodeID) -> None:
        """Register a (uid, axon) pair as serving *node_id*.

        Safe to call from any thread (MetagraphWatcher callbacks run in the
        asyncio loop; ``update_from_responses`` runs in request handlers).
        """
        if axon.ip == "0.0.0.0" or axon.port == 0:
            return
        stake = float(self.metagraph.S[uid]) if uid < len(self.metagraph.S) else 0.0
        with self._lock:
            # Remove stale entry for this uid if it moved to a different node
            old_node = self._uid_to_node.get(uid)
            if old_node is not None and old_node != node_id:
                self._remove_uid_from_node(uid, old_node)
            # Insert into new node's bucket (deduplicate by uid)
            self._uid_to_node[uid] = node_id
            bucket = self._node_to_axons.setdefault(node_id, [])
            # Replace existing entry for this uid if present
            bucket[:] = [(s, u, a) for s, u, a in bucket if u != uid]
            bucket.append((stake, uid, axon))
        log.debug("Indexed miner uid=%d -> node_id=%s (stake=%.2f)", uid, node_id, stake)

    def deindex_miner(self, uid: int) -> None:
        """Remove a miner from the index (called on deregistration)."""
        with self._lock:
            node_id = self._uid_to_node.pop(uid, None)
            if node_id is not None:
                self._remove_uid_from_node(uid, node_id)
        log.debug("Deindexed miner uid=%d", uid)

    def _remove_uid_from_node(self, uid: int, node_id: NodeID) -> None:
        """Remove uid from a node bucket (must be called under self._lock)."""
        bucket = self._node_to_axons.get(node_id)
        if bucket is not None:
            bucket[:] = [(s, u, a) for s, u, a in bucket if u != uid]
            if not bucket:
                del self._node_to_axons[node_id]

    def update_from_responses(
        self,
        responses: list[KnowledgeQuery],
        axons: list[bt.AxonInfo],
    ) -> None:
        """Update the index from a batch of KnowledgeQuery responses.

        Miners self-report their node_id and agent_uid in every response.
        This keeps the index warm without requiring a subtensor commitment
        fetch.  Called after each /enter broadcast.

        *axons* must be the same-length ordered list that was passed to
        bt.Dendrite so we can match responses[i] to axons[i].
        """
        for resp, axon in zip(responses, axons):
            if resp.node_id is None or resp.agent_uid is None:
                continue
            uid: int = int(resp.agent_uid)
            self.index_miner(uid, axon, resp.node_id)

    def node_index_snapshot(self) -> dict[NodeID, list[int]]:
        """Return a read-only copy of the index as {node_id: [uid, ...]}."""
        with self._lock:
            return {
                node_id: [u for _, u, _ in entries]
                for node_id, entries in self._node_to_axons.items()
            }

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

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

    def resolve_miner(self, destination_node_id: NodeID) -> bt.AxonInfo | None:
        """Return the axon for the miner registered at destination_node_id.

        Lookup order:
          1. Check the node index: return highest-stake axon among miners
             explicitly serving this node.
          2. Fall back to the highest-stake active axon in the metagraph
             (preserves original behaviour for nodes with no registered miner).

        Returns None if no active miner is found at all.
        """
        # --- indexed lookup ---
        with self._lock:
            bucket = self._node_to_axons.get(destination_node_id)
            if bucket:
                best = max(bucket, key=lambda t: t[0])
                log.debug(
                    "resolve_miner: node=%s -> uid=%d stake=%.2f (indexed)",
                    destination_node_id,
                    best[1],
                    best[0],
                )
                return best[2]

        # --- metagraph fallback ---
        log.debug(
            "resolve_miner: node=%s not in index, using stake fallback",
            destination_node_id,
        )
        candidates: list[tuple[float, bt.AxonInfo]] = []
        for uid, axon in enumerate(self.metagraph.axons):
            if axon.ip == "0.0.0.0" or axon.port == 0:
                continue
            stake = float(self.metagraph.S[uid])
            candidates.append((stake, axon))

        if not candidates:
            return None

        candidates.sort(key=lambda t: t[0], reverse=True)
        return candidates[0][1]
