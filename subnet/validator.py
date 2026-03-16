"""Narrative Network validator.

Scores miners on four axes (traversal, quality, topology, corpus),
sets weights independently via Yuma Consensus. No custom BFT quorum.
"""

from __future__ import annotations

from copy import copy

import numpy as np

from subnet._bt_compat import _BT_AVAILABLE, get_logger

if _BT_AVAILABLE:
    import bittensor as bt
    import torch
else:
    bt = None  # type: ignore
    torch = None  # type: ignore

from domain.corpus import MerkleProver
from subnet import NETUID, SPEC_VERSION
from subnet.config import (
    CHALLENGE_SAMPLE_SIZE,
    CHOICE_CARD_MIN_COVERAGE,
    CORPUS_WEIGHT,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    EPOCH_SLEEP_S,
    MOVING_AVERAGE_ALPHA,
    QUALITY_WEIGHT,
    TOPOLOGY_WEIGHT,
    TRAVERSAL_WEIGHT,
)
from subnet.emissions import MinerType

if _BT_AVAILABLE:
    from subnet.protocol import KnowledgeQuery, NarrativeHop, WeightCommit
else:
    from subnet.protocol_local import KnowledgeQuery, NarrativeHop  # type: ignore
    WeightCommit = None  # type: ignore

from subnet.reward import (
    score_choice_fairness,
    score_corpus,
    score_quality,
    score_topology,
    score_traversal,
)

_log = get_logger(__name__)


class Validator:
    """Top-level validator runtime."""

    def __init__(
        self,
        config: "bt.Config | None" = None,
        *,
        wallet: "bt.Wallet | None" = None,
        subtensor: "bt.Subtensor | None" = None,
        dendrite: "bt.Dendrite | None" = None,
        metagraph=None,
        graph_store=None,
        embedder=None,
    ):
        if not _BT_AVAILABLE:
            raise ImportError("bittensor is required for production Validator")
        self.config = config or bt.Config()
        self.wallet = wallet or bt.Wallet(config=self.config)
        self.subtensor = subtensor or bt.Subtensor(config=self.config)
        self.metagraph = metagraph or self.subtensor.metagraph(NETUID)
        self.dendrite = dendrite or bt.Dendrite(wallet=self.wallet)

        self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.hotkeys = copy(self.metagraph.hotkeys)
        self.scores = torch.zeros(len(self.metagraph.hotkeys))
        self.step = 0

        # Maps uid -> hex Merkle root string committed by that miner.
        # Populated on first valid corpus challenge; subsequent challenges must
        # match this root or receive a reduced score.
        self._committed_roots: dict[int, str] = {}

        # Cache of detected miner types; entries are evicted on hotkey change in
        # resync_metagraph so newly registered miners are re-classified.
        self._miner_types: dict[int, MinerType] = {}

        # Graph store for topology scoring and edge decay
        if graph_store is not None:
            self.graph_store = graph_store
        else:
            from subnet.graph_store import GraphStore
            self.graph_store = GraphStore(db_path=None)

        # Embedder for real query embeddings (lazy-loads ONNX model on first use).
        # An alternative embedder can be injected for testing.
        if embedder is not None:
            self.embedder = embedder
        else:
            from orchestrator.embedder import Embedder
            self.embedder = Embedder(model_name=EMBEDDING_MODEL)

        # Curated challenge queries covering diverse knowledge domains
        self._challenge_queries = [
            "quantum mechanics fundamentals",
            "climate change ecosystem impacts",
            "machine learning neural networks",
            "ancient Roman history civilization",
            "protein folding biochemistry",
            "economic theory market dynamics",
            "philosophy of consciousness mind",
            "renewable energy solar wind",
            "evolutionary biology natural selection",
            "cryptography blockchain distributed systems",
        ]

    # ------------------------------------------------------------------
    # Metagraph management
    # ------------------------------------------------------------------

    def resync_metagraph(self) -> None:
        previous_hotkeys = copy(self.hotkeys)
        self.metagraph.sync(subtensor=self.subtensor)

        # Resize score array if metagraph grew
        if len(self.metagraph.hotkeys) > len(self.scores):
            new_scores = torch.zeros(len(self.metagraph.hotkeys))
            new_scores[: len(self.scores)] = self.scores
            self.scores = new_scores

        # Reset scores and type cache for UIDs where the hotkey changed
        for uid, (old, new) in enumerate(zip(previous_hotkeys, self.metagraph.hotkeys)):
            if old != new:
                self.scores[uid] = 0
                self._miner_types.pop(uid, None)
                self._committed_roots.pop(uid, None)

        self.hotkeys = copy(self.metagraph.hotkeys)

    # ------------------------------------------------------------------
    # Score accumulation
    # ------------------------------------------------------------------

    def update_scores(self, rewards: torch.FloatTensor, uids: list[int]) -> None:
        if torch.isnan(rewards).any():
            rewards = torch.nan_to_num(rewards, nan=0.0)

        scattered = self.scores.scatter(0, torch.LongTensor(uids), rewards)
        self.scores = MOVING_AVERAGE_ALPHA * scattered + (1 - MOVING_AVERAGE_ALPHA) * self.scores

    # ------------------------------------------------------------------
    # Weight setting (Yuma Consensus — no custom quorum)
    # ------------------------------------------------------------------

    def set_weights(self) -> None:
        norm = torch.norm(self.scores, p=1)
        weights = self.scores / norm if norm != 0 else self.scores
        weights = torch.nan_to_num(weights, nan=0.0)

        response = self.subtensor.set_weights(
            wallet=self.wallet,
            netuid=NETUID,
            uids=self.metagraph.uids,
            weights=weights,
            mechid=0,
            wait_for_inclusion=False,
        )
        if not response.success:
            _log.error(f"set_weights failed: {response.message}")
        else:
            _log.info(f"set_weights success at step {self.step}")

    # ------------------------------------------------------------------
    # Miner type detection
    # ------------------------------------------------------------------

    def _detect_miner_type(
        self,
        uid: int,
        kq_resp: KnowledgeQuery,
        nh_resp: NarrativeHop,
    ) -> MinerType:
        """Classify a miner based on which synapse it responded to.

        Detection rules:
        - KnowledgeQuery returned chunks or merkle_proof AND NarrativeHop
          returned no passage -> DOMAIN miner
        - NarrativeHop returned a passage AND KnowledgeQuery returned no
          chunks/proof -> NARRATIVE miner
        - Both returned valid data -> UNIFIED miner
        - Neither returned valid data -> UNKNOWN (keep existing cache or UNKNOWN)

        The result is cached in self._miner_types[uid] and reused across
        epochs until the hotkey at that UID changes.
        """
        has_kq_response = bool(kq_resp.chunks or kq_resp.merkle_proof)
        has_nh_response = bool(nh_resp.narrative_passage)

        if has_kq_response and has_nh_response:
            detected = MinerType.UNIFIED
        elif has_kq_response:
            detected = MinerType.DOMAIN
        elif has_nh_response:
            detected = MinerType.NARRATIVE
        else:
            # No valid response on either synapse — preserve existing classification
            # if we have one, otherwise mark unknown.
            detected = self._miner_types.get(uid, MinerType.UNKNOWN)

        self._miner_types[uid] = detected
        _log.debug(f"UID {uid} classified as {detected.value}")
        return detected

    # ------------------------------------------------------------------
    # Epoch loop
    # ------------------------------------------------------------------

    async def run_epoch(self) -> None:
        """Run one epoch: challenge miners, score, set weights, decay edges."""
        import random
        import time as _time

        self.resync_metagraph()

        # a) Select UIDs to challenge — miners with serving axons
        serving_uids = [
            uid for uid in range(len(self.metagraph.hotkeys))
            if uid != self.uid
            and hasattr(self.metagraph.axons[uid], "is_serving")
            and self.metagraph.axons[uid].is_serving
        ]
        if not serving_uids:
            _log.warning(f"Epoch {self.step}: no serving miners found")
            self.step += 1
            return

        sample_size = min(CHALLENGE_SAMPLE_SIZE, len(serving_uids))
        challenge_uids = random.sample(serving_uids, sample_size)
        _log.info(f"Epoch {self.step}: challenging UIDs {challenge_uids}")

        # Collect axons for challenged miners
        challenge_axons = [self.metagraph.axons[uid] for uid in challenge_uids]

        # b) Corpus challenges (score_corpus) — sent to all miners; narrative miners
        #    will return no proof and receive corpus_score=1.0 (gate skipped for them).
        corpus_scores: dict[int, float] = {}
        corpus_responses_by_uid: dict[int, KnowledgeQuery] = {}
        corpus_synapse = KnowledgeQuery(query_text="__corpus_challenge__")
        corpus_responses = await self.dendrite(
            axons=challenge_axons,
            synapse=corpus_synapse,
            timeout=12.0,
        )
        for uid, response in zip(challenge_uids, corpus_responses):
            corpus_responses_by_uid[uid] = response
            proof = response.merkle_proof
            if not isinstance(proof, dict):
                corpus_scores[uid] = score_corpus(proof_valid=False)
                continue

            claimed_root = proof.get("root", "")

            # Mathematically verify the hash chain leaf -> siblings -> root.
            proof_valid = MerkleProver.verify(proof, expected_root=claimed_root)

            if proof_valid:
                committed = self._committed_roots.get(uid)
                if committed is None:
                    # First valid proof: pin this root as the committed value.
                    self._committed_roots[uid] = claimed_root
                    root_committed = True
                else:
                    root_committed = claimed_root == committed
                    if not root_committed:
                        _log.warning(
                            f"UID {uid} corpus root changed: expected {committed[:16]}… "
                            f"got {claimed_root[:16]}…"
                        )
            else:
                root_committed = False

            corpus_scores[uid] = score_corpus(
                proof_valid=proof_valid,
                root_committed=root_committed,
            )

        # c) Traversal + Quality scoring + miner type detection via fresh challenges
        traversal_scores: dict[int, float] = {}
        quality_scores: dict[int, float] = {}
        nh_responses_by_uid: dict[int, NarrativeHop] = {}

        test_query_text = random.choice(self._challenge_queries)
        test_query_embedding = self.embedder.embed_one(test_query_text)

        kq_synapse = KnowledgeQuery(
            query_text=test_query_text,
            query_embedding=test_query_embedding,
            top_k=5,
        )
        kq_responses = await self.dendrite(
            axons=challenge_axons,
            synapse=kq_synapse,
            timeout=12.0,
        )

        for uid, kq_resp in zip(challenge_uids, kq_responses):
            start_time = _time.monotonic()

            zero_vec = [0.0] * EMBEDDING_DIM

            if kq_resp.chunks:
                chunk_texts = [
                    c if isinstance(c, str) else (c.get("text") or c.get("content") or "")
                    for c in kq_resp.chunks
                ]
                chunk_texts = [t for t in chunk_texts if t]
                if chunk_texts:
                    chunk_embeddings = self.embedder.embed(chunk_texts)
                    # Mean-pool chunk embeddings to get a single representative vector
                    arr = np.array(chunk_embeddings, dtype=float)
                    mean_vec = (arr.mean(axis=0)).tolist()
                    chunks_embedding = mean_vec
                    domain_centroid = mean_vec
                else:
                    chunks_embedding = zero_vec
                    domain_centroid = zero_vec
            else:
                chunks_embedding = zero_vec
                domain_centroid = zero_vec

            process_time = _time.monotonic() - start_time

            nh_synapse = NarrativeHop(
                destination_node_id=kq_resp.node_id or f"node-{uid}",
                player_path=[],
                retrieved_chunks=kq_resp.chunks or [],
                session_id=f"epoch-{self.step}-uid-{uid}",
            )
            nh_responses = await self.dendrite(
                axons=[self.metagraph.axons[uid]],
                synapse=nh_synapse,
                timeout=12.0,
            )
            nh_resp = nh_responses[0] if nh_responses else nh_synapse
            nh_responses_by_uid[uid] = nh_resp

            # Detect miner type from this epoch's responses
            miner_type = self._detect_miner_type(uid, kq_resp, nh_resp)

            passage_embedding = nh_resp.passage_embedding or [0.0] * EMBEDDING_DIM

            # Domain miners: score on traversal (chunk quality) only; narrative quality
            # uses a neutral passage embedding since they don't generate narrative.
            # Narrative miners: score on narrative quality; traversal uses neutral values
            # since they don't retrieve chunks.
            # Unified / Unknown: score on all axes as designed.
            if miner_type == MinerType.DOMAIN:
                traversal_scores[uid] = score_traversal(
                    chunks_embedding=chunks_embedding,
                    query_embedding=test_query_embedding,
                    domain_centroid=domain_centroid,
                    passage_embedding=zero_vec,  # no passage; neutral
                    process_time=process_time,
                )
                quality_scores[uid] = 0.5  # neutral; domain miners don't produce narrative
            elif miner_type == MinerType.NARRATIVE:
                traversal_scores[uid] = 0.5  # neutral; narrative miners don't retrieve chunks
                raw_quality = score_quality(
                    passage_embedding=passage_embedding,
                    path_embeddings=[],
                    destination_centroid=domain_centroid,
                    source_centroid=test_query_embedding,
                    passage_text=nh_resp.narrative_passage or "",
                )
                # Apply choice card fairness multiplier: penalise miners that omit
                # adjacent nodes from their choice cards (traffic-steering attack).
                offered_ids = [
                    c.destination_node_id
                    for c in (nh_resp.choice_cards or [])
                ]
                adjacent_ids = self.graph_store.neighbours(nh_synapse.destination_node_id)
                fairness = score_choice_fairness(offered_ids, adjacent_ids)
                if fairness < CHOICE_CARD_MIN_COVERAGE:
                    _log.debug(
                        f"UID {uid} choice card fairness {fairness:.3f} < "
                        f"{CHOICE_CARD_MIN_COVERAGE} — applying quality penalty"
                    )
                quality_scores[uid] = raw_quality * fairness
            else:
                # UNIFIED or UNKNOWN: score on all axes
                traversal_scores[uid] = score_traversal(
                    chunks_embedding=chunks_embedding,
                    query_embedding=test_query_embedding,
                    domain_centroid=domain_centroid,
                    passage_embedding=passage_embedding,
                    process_time=process_time,
                )
                raw_quality = score_quality(
                    passage_embedding=passage_embedding,
                    path_embeddings=[],
                    destination_centroid=domain_centroid,
                    source_centroid=test_query_embedding,
                    passage_text=nh_resp.narrative_passage or "",
                )
                # Apply choice card fairness multiplier for unified miners too
                offered_ids = [
                    c.destination_node_id
                    for c in (nh_resp.choice_cards or [])
                ]
                adjacent_ids = self.graph_store.neighbours(nh_synapse.destination_node_id)
                fairness = score_choice_fairness(offered_ids, adjacent_ids)
                if fairness < CHOICE_CARD_MIN_COVERAGE:
                    _log.debug(
                        f"UID {uid} choice card fairness {fairness:.3f} < "
                        f"{CHOICE_CARD_MIN_COVERAGE} — applying quality penalty"
                    )
                quality_scores[uid] = raw_quality * fairness

            # Reinforce the edge traversed and record it for audit/replay
            source_node_id = f"source-{self.step}"
            dest_node_id = nh_synapse.destination_node_id
            q_score = quality_scores[uid]
            self.graph_store.reinforce_edge(source_node_id, dest_node_id, q_score)
            self.graph_store.log_traversal(
                session_id=f"epoch-{self.step}-uid-{uid}",
                source_id=source_node_id,
                dest_id=dest_node_id,
                passage_embedding=passage_embedding,
                scores={uid: q_score},
            )

        # d) Topology scoring from graph store
        topology_scores: dict[int, float] = {}
        for uid in challenge_uids:
            node_id = f"node-{uid}"
            bc = self.graph_store.betweenness_centrality(node_id)
            ew = self.graph_store.outgoing_edge_weight_sum(node_id)
            topology_scores[uid] = score_topology(
                betweenness_centrality=bc,
                outgoing_edge_weight_sum=ew,
            )

        # e) Aggregate via EmissionCalculator — pass miner_type so corpus gate is
        #    bypassed for narrative miners that legitimately have no corpus.
        from subnet.emissions import EmissionCalculator, MinerScoreSnapshot

        snapshots = []
        for uid in challenge_uids:
            uid_type = self._miner_types.get(uid, MinerType.UNKNOWN)
            # Narrative miners default corpus_score to 1.0 (pass) since they have
            # no corpus; the gate does not apply to them in EmissionCalculator.
            if uid_type == MinerType.NARRATIVE:
                c_score = 1.0
            else:
                c_score = corpus_scores.get(uid, 0.0)
            snapshots.append(MinerScoreSnapshot(
                uid=uid,
                traversal_score=traversal_scores.get(uid, 0.0),
                quality_score=quality_scores.get(uid, 0.0),
                topology_score=topology_scores.get(uid, 0.0),
                corpus_score=c_score,
                traversal_count=1,
                miner_type=uid_type,
            ))

        calculator = EmissionCalculator()
        weights = calculator.compute(snapshots)

        rewards = torch.zeros(len(challenge_uids))
        for i, w in enumerate(weights):
            rewards[i] = w

        self.update_scores(rewards, challenge_uids)
        self.set_weights()

        # Decay edges
        self.graph_store.decay_edges()

        type_summary = {
            t.value: sum(1 for uid in challenge_uids if self._miner_types.get(uid) == t)
            for t in MinerType
            if any(self._miner_types.get(uid) == t for uid in challenge_uids)
        }
        _log.info(
            f"Epoch {self.step}: scored {len(challenge_uids)} miners "
            f"{type_summary}, weights set, edges decayed"
        )
        self.step += 1

    def run_forever(self) -> None:
        import asyncio
        import time

        _log.info("Validator starting run_forever loop")
        while True:
            try:
                asyncio.get_event_loop().run_until_complete(self.run_epoch())
            except Exception as e:
                _log.error(f"Epoch failed: {e}")
            time.sleep(EPOCH_SLEEP_S)


# ------------------------------------------------------------------
# Local dev validator — no Bittensor registration required
# ------------------------------------------------------------------


class LocalValidator:
    """Validator that runs against the local seed topology without Bittensor."""

    def __init__(self) -> None:
        import logging

        self.log = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)

        self.log.info("Loading seed topology for local validator...")
        from seed.loader import load_topology
        from subnet.graph_store import GraphStore

        self.graph_store, self.corpus_map = load_topology()
        self.step = 0

        node_ids = self.graph_store.get_live_node_ids()
        self.log.info(
            "Local validator ready: %d nodes, scoring with mock heuristics",
            len(node_ids),
        )

    def run_epoch(self) -> None:
        """Score all nodes using mock heuristics, decay edges, log results."""
        import time

        from orchestrator.mock_scoring import mock_scores

        node_ids = self.graph_store.get_live_node_ids()
        epoch_scores: dict[str, dict[str, float]] = {}

        for node_id in node_ids:
            scores = mock_scores(
                chunk_scores=[0.5],  # placeholder
                passage_text="mock passage for scoring epoch",
                node_id=node_id,
                graph_store=self.graph_store,
            )
            epoch_scores[node_id] = scores

        # Decay edges
        self.graph_store.decay_edges()

        # Log results
        self.log.info(
            "Epoch %d: scored %d nodes, edges decayed",
            self.step, len(node_ids),
        )
        for node_id, scores in epoch_scores.items():
            self.log.info(
                "  %s: trav=%.3f qual=%.3f topo=%.3f corp=%.3f",
                node_id, scores["traversal"], scores["quality"],
                scores["topology"], scores["corpus"],
            )
        self.step += 1

    def run_forever(self) -> None:
        import time

        self.log.info("Local validator starting epoch loop (every %ds)", EPOCH_SLEEP_S)
        while True:
            try:
                self.run_epoch()
            except Exception as e:
                self.log.error("Epoch failed: %s", e)
            time.sleep(EPOCH_SLEEP_S)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    import os

    if os.environ.get("AXON_NETWORK") == "local":
        validator = LocalValidator()
    else:
        validator = Validator()
    validator.run_forever()
