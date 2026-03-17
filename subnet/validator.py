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
else:
    bt = None  # type: ignore

from domain.corpus import MerkleProver
from subnet import NETUID
from subnet.config import (
    CHALLENGE_SAMPLE_SIZE,
    CHOICE_CARD_MIN_COVERAGE,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    EPOCH_SLEEP_S,
    MOVING_AVERAGE_ALPHA,
    NODE_REGISTRATION_ENABLED,
    PRUNING_ENABLED,
    PRUNING_EPOCH_INTERVAL,
)

try:
    from evolution.pruning import EpochScore, PruningEngine
except ImportError:
    PruningEngine = None  # type: ignore
    EpochScore = None  # type: ignore

try:
    from evolution.integration import IntegrationManager
    from evolution.nla_settlement import NLASettlementClient
    from evolution.voting import BondReturn, VotingEngine
except ImportError:
    IntegrationManager = None  # type: ignore
    NLASettlementClient = None  # type: ignore
    BondReturn = None  # type: ignore
    VotingEngine = None  # type: ignore

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
        self.scores = np.zeros(len(self.metagraph.hotkeys), dtype=np.float32)
        self.step = 0

        # Maps uid -> hex Merkle root string committed by that miner.
        # Populated on first valid corpus challenge; subsequent challenges must
        # match this root or receive a reduced score.
        self._committed_roots: dict[int, str] = {}

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

        # uid -> graph node_id mapping, populated from manifest registration
        self._uid_to_node_id: dict[int, str] = {}

        # Shared NLA client for all evolution components
        self._nla_client = NLASettlementClient() if NLASettlementClient is not None else None

        # Integration manager (ramp-in of accepted proposals)
        self.integration_manager = (
            IntegrationManager(nla_client=self._nla_client)
            if IntegrationManager is not None else None
        )

        # Pruning engine — exempt nodes currently in integration pipeline
        exempt_fn = (
            self.integration_manager.integrating_node_ids
            if self.integration_manager is not None else None
        )
        self.pruning_engine = (
            PruningEngine(nla_client=self._nla_client, exempt_node_ids_fn=exempt_fn)
            if PruningEngine is not None else None
        )

        # Voting engine (tallies votes and finalises proposals each epoch)
        self.voting_engine = (
            VotingEngine(
                subtensor=self.subtensor,
                netuid=NETUID,
                nla_client=self._nla_client,
            )
            if VotingEngine is not None else None
        )

        # Bond return handler (returns/burns bonds after vote outcomes)
        self.bond_return = (
            BondReturn(subtensor=self.subtensor, nla_client=self._nla_client)
            if BondReturn is not None else None
        )

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
            new_scores = np.zeros(len(self.metagraph.hotkeys), dtype=np.float32)
            new_scores[: len(self.scores)] = self.scores
            self.scores = new_scores

        # Reset scores for UIDs where the hotkey changed
        for uid, (old, new) in enumerate(zip(previous_hotkeys, self.metagraph.hotkeys)):
            if old != new:
                self.scores[uid] = 0
                self._committed_roots.pop(uid, None)

        self.hotkeys = copy(self.metagraph.hotkeys)

    # ------------------------------------------------------------------
    # Score accumulation
    # ------------------------------------------------------------------

    def update_scores(self, rewards: np.ndarray, uids: list[int]) -> None:
        if np.isnan(rewards).any():
            rewards = np.nan_to_num(rewards, nan=0.0)

        scattered = self.scores.copy()
        scattered[uids] = rewards
        self.scores = MOVING_AVERAGE_ALPHA * scattered + (1 - MOVING_AVERAGE_ALPHA) * self.scores

    # ------------------------------------------------------------------
    # Weight setting (Yuma Consensus — no custom quorum)
    # ------------------------------------------------------------------

    def set_weights(self) -> None:
        norm = np.linalg.norm(self.scores, ord=1)
        weights = self.scores / norm if norm != 0 else self.scores
        weights = np.nan_to_num(weights, nan=0.0)

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
    # Epoch loop
    # ------------------------------------------------------------------

    async def run_epoch(self) -> None:
        """Run one epoch: challenge miners, score, set weights, decay edges."""
        import random
        import time as _time

        self.resync_metagraph()

        # Register nodes from miner manifests
        if NODE_REGISTRATION_ENABLED:
            serving_uids_pre = [
                uid for uid in range(len(self.metagraph.hotkeys))
                if uid != self.uid
                and hasattr(self.metagraph.axons[uid], "is_serving")
                and self.metagraph.axons[uid].is_serving
            ]
            self._register_manifests(serving_uids_pre)

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
                destination_node_id=kq_resp.node_id or self._uid_to_node_id.get(uid, f"node-{uid}"),
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

            passage_embedding = nh_resp.passage_embedding or [0.0] * EMBEDDING_DIM

            # Score every miner on all four axes unconditionally
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
            node_id = self._uid_to_node_id.get(uid, f"node-{uid}")
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

        rewards = np.zeros(len(challenge_uids), dtype=np.float32)
        for i, w in enumerate(weights):
            rewards[i] = w

        self.update_scores(rewards, challenge_uids)
        self.set_weights()

        # Decay edges
        self.graph_store.decay_edges()

        # Feed scores to pruning engine and run periodic pruning
        if PRUNING_ENABLED and self.pruning_engine is not None:
            epoch_scores: dict[str, EpochScore] = {}
            for uid in challenge_uids:
                node_id = self._uid_to_node_id.get(uid, f"node-{uid}")
                epoch_scores[node_id] = EpochScore(
                    epoch=self.step,
                    node_id=node_id,
                    score=quality_scores.get(uid, 0.0),
                    traversal_count=1,
                )
            self.pruning_engine.push_scores(self.step, epoch_scores)

            if self.step % PRUNING_EPOCH_INTERVAL == 0:
                collapses = self.pruning_engine.process_epoch(self.step)
                for collapse in collapses:
                    self.graph_store.set_node_state(collapse.node_id, "Pruned")
                    _log.warning("Node %s pruned: %s", collapse.node_id, collapse.reason)

        # --- Evolution: voting finalisation and integration advancement ---
        current_block = None
        try:
            current_block = self.subtensor.get_current_block()
        except Exception as exc:
            _log.warning("Could not fetch current block for evolution: %s", exc)

        if current_block is not None:
            # Finalise any proposals whose voting window has closed
            if self.voting_engine is not None:
                tally_results = self.voting_engine.process_epoch(current_block)
                for result in tally_results:
                    proposal = self.voting_engine._proposals.get(result.proposal_id)
                    if proposal is None:
                        continue
                    if result.passed and self.bond_return is not None:
                        self.bond_return.return_bond(proposal)
                        if self.integration_manager is not None:
                            self.integration_manager.enqueue(proposal, current_block)
                    elif not result.passed and self.bond_return is not None:
                        self.bond_return.burn_bond(proposal)

            # Advance integration pipeline for nodes in ramp-in
            if self.integration_manager is not None:
                node_scores_for_integration: dict[str, float] = {}
                for uid in challenge_uids:
                    node_id = self._uid_to_node_id.get(uid, f"node-{uid}")
                    node_scores_for_integration[node_id] = quality_scores.get(uid, 0.0)
                newly_live = self.integration_manager.process_epoch(
                    current_block, node_scores_for_integration,
                )
                for node_id in newly_live:
                    self.graph_store.set_node_state(node_id, "Live")
                    _log.info("Node %s completed integration and is now LIVE", node_id)
                    if self.pruning_engine is not None:
                        self.pruning_engine.register_node(node_id)

        # FUTURE: Comparative attestation -- head-to-head miner comparison scoring
        # FUTURE: LLM adversarial controls -- detect and penalize gaming of narrative quality

        _log.info(
            f"Epoch {self.step}: scored {len(challenge_uids)} miners, weights set, edges decayed"
        )
        self.step += 1

    def _register_manifests(self, serving_uids: list[int]) -> None:
        """Check serving miners for manifest commitments and register new nodes."""
        from domain.manifest import ManifestStore

        manifest_store = ManifestStore()

        for uid in serving_uids:
            # Skip if already mapped
            if uid in self._uid_to_node_id:
                continue

            try:
                manifest_cid = self.subtensor.get_commitment(NETUID, uid)
            except Exception:
                continue

            if not manifest_cid:
                continue

            manifest = manifest_store.load(manifest_cid)
            if manifest is None:
                _log.debug("Manifest CID %s for UID %d not found locally", manifest_cid[:16], uid)
                continue

            node_id = manifest.node_id
            self._uid_to_node_id[uid] = node_id

            # Register in graph store if new
            existing = self.graph_store.get_node(node_id)
            if existing is None:
                self.graph_store.add_node(
                    node_id, state="Live",
                    metadata={"miner_uid": uid, "miner_hotkey": manifest.miner_hotkey},
                )
                if self.pruning_engine is not None:
                    self.pruning_engine.register_node(node_id)
                _log.info(
                    "Registered node %s for UID %d from manifest %s",
                    node_id, uid, manifest_cid[:16],
                )

    def run_forever(self) -> None:
        import asyncio
        import time

        _log.info("Validator starting run_forever loop")
        while True:
            try:
                asyncio.run(self.run_epoch())
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

        from subnet.events import get_event_bus, emit  # noqa: F401 — used in run_epoch

        self.log = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
        self._event_bus_initialized = False

        from seed.loader import load_topology
        from subnet.harness import create_local_network

        self.graph_store, self.corpus_map = load_topology()
        node_ids = self.graph_store.get_live_node_ids()

        harness = create_local_network(
            n_miners=len(node_ids),
            graph_node_ids=node_ids,
        )
        self.metagraph = harness["metagraph"]
        self.dendrite = harness["dendrite"]
        self.subtensor = harness["subtensor"]
        self.embedder = harness["embedder"]

        self.scores = [0.0] * len(self.metagraph.hotkeys)
        self.step = 0

        # uid -> graph node_id mapping (local mode: no manifest registration)
        self._uid_to_node_id: dict[int, str] = {}

        # Pruning engine (nla_client=None — NLA settlement not yet wired)
        self.pruning_engine = PruningEngine(nla_client=None) if PruningEngine is not None else None

        self.log.info(
            "Local validator ready: %d nodes, real scoring via reward.py",
            len(node_ids),
        )

    async def run_epoch(self) -> None:
        """Run one epoch using real scoring through mock dendrite."""
        import random
        import time as _time

        from subnet.emissions import EmissionCalculator, MinerScoreSnapshot

        node_ids = self.graph_store.get_live_node_ids()
        if not node_ids:
            self.log.warning("Epoch %d: no live nodes", self.step)
            self.step += 1
            return

        # Select serving UIDs (skip UID 0 = validator)
        serving_uids = [
            uid for uid in range(1, len(self.metagraph.hotkeys))
            if self.metagraph.axons[uid].is_serving
        ]

        sample_size = min(CHALLENGE_SAMPLE_SIZE, len(serving_uids))
        challenge_uids = (
            random.sample(serving_uids, sample_size)
            if sample_size < len(serving_uids)
            else serving_uids
        )
        challenge_axons = [self.metagraph.axons[uid] for uid in challenge_uids]

        self.log.info("Epoch %d: challenging UIDs %s", self.step, challenge_uids)

        # Lazy event bus init + epoch.started
        if not self._event_bus_initialized:
            import os
            from subnet.events import get_event_bus
            await get_event_bus(os.environ.get("REDIS_URL"))
            self._event_bus_initialized = True

        from subnet.events import emit
        await emit("epoch.started", "validator", {
            "epoch": self.step,
            "challenge_uids": challenge_uids,
            "query_text": test_query,
        }, correlation_id=f"epoch-{self.step}")

        zero_vec = [0.0] * EMBEDDING_DIM

        # a) Corpus challenges
        corpus_scores: dict[int, float] = {}
        corpus_synapse = KnowledgeQuery(query_text="__corpus_challenge__")
        corpus_responses = await self.dendrite(
            axons=challenge_axons, synapse=corpus_synapse, timeout=12.0,
        )
        for uid, response in zip(challenge_uids, corpus_responses):
            proof = response.merkle_proof
            if isinstance(proof, dict):
                corpus_scores[uid] = score_corpus(proof_valid=True, root_committed=True)
            else:
                corpus_scores[uid] = score_corpus(proof_valid=False)

        # b) Traversal + Quality scoring
        traversal_scores: dict[int, float] = {}
        quality_scores: dict[int, float] = {}

        test_query = random.choice([
            "quantum mechanics fundamentals",
            "climate change ecosystem impacts",
            "machine learning neural networks",
        ])
        test_embedding = self.embedder.embed_one(test_query)

        kq_synapse = KnowledgeQuery(
            query_text=test_query, query_embedding=test_embedding, top_k=5,
        )
        kq_responses = await self.dendrite(
            axons=challenge_axons, synapse=kq_synapse, timeout=12.0,
        )

        for uid, kq_resp in zip(challenge_uids, kq_responses):
            start_time = _time.monotonic()

            if kq_resp.chunks:
                chunk_texts = [
                    c.get("text", "") if isinstance(c, dict) else str(c)
                    for c in kq_resp.chunks
                ]
                chunk_texts = [t for t in chunk_texts if t]
                if chunk_texts:
                    chunk_embeddings = self.embedder.embed(chunk_texts)
                    arr = np.array(chunk_embeddings, dtype=float)
                    mean_vec = arr.mean(axis=0).tolist()
                    chunks_embedding = mean_vec
                    domain_centroid = mean_vec
                else:
                    chunks_embedding = zero_vec
                    domain_centroid = zero_vec
            else:
                chunks_embedding = zero_vec
                domain_centroid = zero_vec

            process_time = _time.monotonic() - start_time

            # Fire narrative hop
            nh_synapse = NarrativeHop(
                destination_node_id=kq_resp.node_id or self._uid_to_node_id.get(uid, f"node-{uid}"),
                player_path=[],
                retrieved_chunks=kq_resp.chunks or [],
                session_id=f"epoch-{self.step}-uid-{uid}",
            )
            nh_responses = await self.dendrite(
                axons=[self.metagraph.axons[uid]], synapse=nh_synapse, timeout=12.0,
            )
            nh_resp = nh_responses[0] if nh_responses else nh_synapse

            passage_embedding = nh_resp.passage_embedding or zero_vec

            # Score traversal
            traversal_scores[uid] = score_traversal(
                chunks_embedding=chunks_embedding,
                query_embedding=test_embedding,
                domain_centroid=domain_centroid,
                passage_embedding=passage_embedding,
                process_time=process_time,
            )

            # Score quality with choice card fairness
            raw_quality = score_quality(
                passage_embedding=passage_embedding,
                path_embeddings=[],
                destination_centroid=domain_centroid,
                source_centroid=test_embedding,
                passage_text=nh_resp.narrative_passage or "",
            )
            offered_ids = [c.destination_node_id for c in (nh_resp.choice_cards or [])]
            adjacent_ids = self.graph_store.neighbours(nh_synapse.destination_node_id)
            fairness = score_choice_fairness(offered_ids, adjacent_ids)
            quality_scores[uid] = raw_quality * fairness

            # Reinforce edge
            dest_node_id = nh_synapse.destination_node_id
            self.graph_store.reinforce_edge(
                f"source-{self.step}", dest_node_id, quality_scores[uid],
            )

        # c) Topology scoring
        topology_scores: dict[int, float] = {}
        for uid in challenge_uids:
            node_id = self._uid_to_node_id.get(uid, f"node-{uid}")
            bc = self.graph_store.betweenness_centrality(node_id)
            ew = self.graph_store.outgoing_edge_weight_sum(node_id)
            topology_scores[uid] = score_topology(
                betweenness_centrality=bc, outgoing_edge_weight_sum=ew,
            )

        # d) Aggregate via EmissionCalculator (pure Python)
        snapshots = [
            MinerScoreSnapshot(
                uid=uid,
                traversal_score=traversal_scores.get(uid, 0.0),
                quality_score=quality_scores.get(uid, 0.0),
                topology_score=topology_scores.get(uid, 0.0),
                corpus_score=corpus_scores.get(uid, 0.0),
                traversal_count=1,
            )
            for uid in challenge_uids
        ]

        calculator = EmissionCalculator()
        weights = calculator.compute(snapshots)

        # e) Set weights (MockSubtensor records calls, no torch needed)
        weight_dict = {uid: w for uid, w in zip(challenge_uids, weights)}
        self.subtensor.set_weights(
            netuid=0, uids=challenge_uids, weights=list(weight_dict.values()),
        )

        # f) Update local scores (pure Python moving average)
        alpha = 0.1
        for uid, w in zip(challenge_uids, weights):
            if uid < len(self.scores):
                self.scores[uid] = alpha * w + (1 - alpha) * self.scores[uid]

        # Decay edges
        self.graph_store.decay_edges()

        # Feed scores to pruning engine and run periodic pruning
        # Local mode: no manifest registration (no subtensor)
        if PRUNING_ENABLED and self.pruning_engine is not None:
            epoch_scores_local: dict[str, EpochScore] = {}
            for uid in challenge_uids:
                node_id = self._uid_to_node_id.get(uid, f"node-{uid}")
                epoch_scores_local[node_id] = EpochScore(
                    epoch=self.step,
                    node_id=node_id,
                    score=quality_scores.get(uid, 0.0),
                    traversal_count=1,
                )
            self.pruning_engine.push_scores(self.step, epoch_scores_local)

            if self.step % PRUNING_EPOCH_INTERVAL == 0:
                collapses = self.pruning_engine.process_epoch(self.step)
                for collapse in collapses:
                    self.graph_store.set_node_state(collapse.node_id, "Pruned")
                    self.log.warning("Node %s pruned: %s", collapse.node_id, collapse.reason)

        self.log.info(
            "Epoch %d: scored %d miners via real reward.py pipeline",
            self.step, len(challenge_uids),
        )
        for uid in challenge_uids:
            self.log.info(
                "  UID %d: trav=%.3f qual=%.3f topo=%.3f corp=%.3f weight=%.4f",
                uid,
                traversal_scores.get(uid, 0),
                quality_scores.get(uid, 0),
                topology_scores.get(uid, 0),
                corpus_scores.get(uid, 0),
                weight_dict.get(uid, 0),
            )
        self.step += 1

    def run_forever(self) -> None:
        import asyncio
        import time

        self.log.info("Local validator starting epoch loop (every %ds)", EPOCH_SLEEP_S)
        while True:
            try:
                asyncio.run(self.run_epoch())
            except Exception as e:
                self.log.error("Epoch failed: %s", e, exc_info=True)
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
