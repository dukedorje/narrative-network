"""Narrative Network validator.

Scores miners on four axes (traversal, quality, topology, corpus),
sets weights independently via Yuma Consensus. No custom BFT quorum.
"""

from __future__ import annotations

from copy import copy

import bittensor as bt
import torch

from subnet import NETUID, SPEC_VERSION
from subnet.config import (
    CHALLENGE_SAMPLE_SIZE,
    CORPUS_WEIGHT,
    EPOCH_SLEEP_S,
    MOVING_AVERAGE_ALPHA,
    QUALITY_WEIGHT,
    TOPOLOGY_WEIGHT,
    TRAVERSAL_WEIGHT,
)
from subnet.protocol import KnowledgeQuery, NarrativeHop, WeightCommit
from subnet.reward import score_corpus, score_quality, score_topology, score_traversal


class Validator:
    """Top-level validator runtime."""

    def __init__(
        self,
        config: bt.Config | None = None,
        *,
        wallet: bt.Wallet | None = None,
        subtensor: bt.Subtensor | None = None,
        dendrite: bt.Dendrite | None = None,
        metagraph=None,
        graph_store=None,
    ):
        self.config = config or bt.Config()
        self.wallet = wallet or bt.Wallet(config=self.config)
        self.subtensor = subtensor or bt.Subtensor(config=self.config)
        self.metagraph = metagraph or self.subtensor.metagraph(NETUID)
        self.dendrite = dendrite or bt.Dendrite(wallet=self.wallet)

        self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.hotkeys = copy(self.metagraph.hotkeys)
        self.scores = torch.zeros(len(self.metagraph.hotkeys))
        self.step = 0

        # Graph store for topology scoring and edge decay
        if graph_store is not None:
            self.graph_store = graph_store
        else:
            from subnet.graph_store import GraphStore
            self.graph_store = GraphStore(db_path=None)

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

        # Reset scores for UIDs where the hotkey changed
        for uid, (old, new) in enumerate(zip(previous_hotkeys, self.metagraph.hotkeys)):
            if old != new:
                self.scores[uid] = 0

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
            bt.logging.error(f"set_weights failed: {response.message}")
        else:
            bt.logging.info(f"set_weights success at step {self.step}")

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
            bt.logging.warning(f"Epoch {self.step}: no serving miners found")
            self.step += 1
            return

        sample_size = min(CHALLENGE_SAMPLE_SIZE, len(serving_uids))
        challenge_uids = random.sample(serving_uids, sample_size)
        bt.logging.info(f"Epoch {self.step}: challenging UIDs {challenge_uids}")

        # Collect axons for challenged miners
        challenge_axons = [self.metagraph.axons[uid] for uid in challenge_uids]

        # b) Corpus challenges (score_corpus)
        corpus_scores: dict[int, float] = {}
        corpus_synapse = KnowledgeQuery(query_text="__corpus_challenge__")
        corpus_responses = await self.dendrite(
            axons=challenge_axons,
            synapse=corpus_synapse,
            timeout=12.0,
        )
        for uid, response in zip(challenge_uids, corpus_responses):
            if response.merkle_proof is not None:
                has_valid_structure = (
                    isinstance(response.merkle_proof, dict)
                    and "leaf_hash" in response.merkle_proof
                    and "siblings" in response.merkle_proof
                    and "root" in response.merkle_proof
                )
                corpus_scores[uid] = score_corpus(merkle_root_matches=has_valid_structure)
            else:
                corpus_scores[uid] = score_corpus(merkle_root_matches=False)

        # c) Traversal + Quality scoring via fresh challenges
        traversal_scores: dict[int, float] = {}
        quality_scores: dict[int, float] = {}

        test_query_text = "quantum mechanics fundamentals"
        test_query_embedding = [0.0] * 768  # placeholder

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

            chunks_embedding = [0.0] * 768
            domain_centroid = [0.0] * 768

            if kq_resp.chunks:
                if kq_resp.domain_similarity is not None:
                    domain_centroid = test_query_embedding  # approximation

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

            passage_embedding = nh_resp.passage_embedding or [0.0] * 768
            traversal_scores[uid] = score_traversal(
                chunks_embedding=chunks_embedding,
                query_embedding=test_query_embedding,
                domain_centroid=domain_centroid,
                passage_embedding=passage_embedding,
                process_time=process_time,
            )

            quality_scores[uid] = score_quality(
                passage_embedding=passage_embedding,
                path_embeddings=[],
                destination_centroid=domain_centroid,
                source_centroid=[0.0] * 768,
                passage_text=nh_resp.narrative_passage or "",
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

        # e) Aggregate via EmissionCalculator
        from subnet.emissions import EmissionCalculator, MinerScoreSnapshot

        snapshots = []
        for uid in challenge_uids:
            snapshots.append(MinerScoreSnapshot(
                uid=uid,
                traversal_score=traversal_scores.get(uid, 0.0),
                quality_score=quality_scores.get(uid, 0.0),
                topology_score=topology_scores.get(uid, 0.0),
                corpus_score=corpus_scores.get(uid, 0.0),
                traversal_count=1,
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

        bt.logging.info(
            f"Epoch {self.step}: scored {len(challenge_uids)} miners, "
            f"weights set, edges decayed"
        )
        self.step += 1

    def run_forever(self) -> None:
        import asyncio
        import time

        bt.logging.info("Validator starting run_forever loop")
        while True:
            try:
                asyncio.get_event_loop().run_until_complete(self.run_epoch())
            except Exception as e:
                bt.logging.error(f"Epoch failed: {e}")
            time.sleep(EPOCH_SLEEP_S)


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    validator = Validator()
    validator.run_forever()
