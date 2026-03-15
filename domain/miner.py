"""Domain miner — serves corpus chunks and Merkle proofs.

One instance per registered node ID. Handles KnowledgeQuery synapses.
"""

from __future__ import annotations

import asyncio
import logging
import time

import bittensor as bt
import numpy as np

from subnet import NETUID
from subnet.config import (
    EMBEDDING_MODEL,
    SubnetConfig,
    UNBROWSE_CORPUS_THRESHOLD,
)
from subnet.protocol import KnowledgeQuery
from domain.corpus import Chunk, CorpusLoader, MerkleProver, compute_corpus_root_hash

log = logging.getLogger(__name__)


class DomainMiner:
    """Domain miner: corpus retrieval and Merkle proof service."""

    def __init__(
        self,
        config: bt.Config | None = None,
        corpus_dir: str | None = None,
        node_id: str | None = None,
        whitelist_hotkeys: list[str] | None = None,
    ) -> None:
        self.config = config or bt.Config()
        self.wallet = bt.Wallet(config=self.config)
        self.subtensor = bt.Subtensor(config=self.config)
        self.metagraph = self.subtensor.metagraph(NETUID)
        self.uid: int = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.node_id: str = node_id or f"node-{self.uid}"
        self.whitelist_hotkeys: set[str] = set(whitelist_hotkeys or [])

        # Corpus + Merkle
        self.chunks: list[Chunk] = []
        self.merkle_prover: MerkleProver | None = None
        self.corpus_root_hash: str = ""
        self.centroid: list[float] = []

        if corpus_dir:
            self._load_corpus(corpus_dir)

        from orchestrator.unbrowse import UnbrowseClient
        self._unbrowse = UnbrowseClient()

        self.axon = bt.Axon(wallet=self.wallet, config=self.config)
        self.axon.attach(
            forward_fn=self._forward,
            blacklist_fn=self._blacklist,
            priority_fn=self._priority,
        )

    # ------------------------------------------------------------------
    # Corpus loading
    # ------------------------------------------------------------------

    def _load_corpus(self, corpus_dir: str) -> None:
        log.info("Loading corpus from %s", corpus_dir)
        loader = CorpusLoader(
            corpus_dir=corpus_dir,
            model_name=EMBEDDING_MODEL,
        )
        self.chunks = loader.load()
        self.centroid = loader.centroid
        self.merkle_prover = MerkleProver(self.chunks)
        self.corpus_root_hash = self.merkle_prover.root
        log.info(
            "Corpus loaded: %d chunks, root=%s…",
            len(self.chunks),
            self.corpus_root_hash[:16],
        )

    # ------------------------------------------------------------------
    # Axon handlers
    # ------------------------------------------------------------------

    async def _forward(self, synapse: KnowledgeQuery) -> KnowledgeQuery:
        """Handle KnowledgeQuery — chunk retrieval or corpus challenge."""
        if synapse.query_text == "__corpus_challenge__":
            if self.merkle_prover and self.chunks:
                # Return proof for a random chunk as integrity challenge response
                import random
                idx = random.randrange(len(self.chunks))
                proof = self.merkle_prover.prove(idx)
                synapse.merkle_proof = proof
                synapse.node_id = self.node_id
                synapse.agent_uid = self.uid
            return synapse

        # Semantic retrieval
        if not self.chunks:
            synapse.chunks = []
            synapse.domain_similarity = 0.0
            synapse.node_id = self.node_id
            synapse.agent_uid = self.uid
            return synapse

        query_emb = np.array(synapse.query_embedding, dtype=np.float32)
        if query_emb.shape[0] == 0:
            synapse.chunks = []
            synapse.domain_similarity = 0.0
            synapse.node_id = self.node_id
            synapse.agent_uid = self.uid
            return synapse

        # Score all chunks by cosine similarity
        chunk_embs = np.array([c.embedding for c in self.chunks], dtype=np.float32)
        scores = chunk_embs @ query_emb  # embeddings are pre-normalised
        top_k = min(synapse.top_k, len(self.chunks))
        top_indices = np.argpartition(scores, -top_k)[-top_k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        synapse.chunks = [
            {
                "id": self.chunks[i].id,
                "text": self.chunks[i].text,
                "hash": self.chunks[i].hash,
                "score": float(scores[i]),
                "char_start": self.chunks[i].char_start,
                "char_end": self.chunks[i].char_end,
            }
            for i in top_indices
        ]

        # Domain similarity: cosine between query and corpus centroid
        if self.centroid:
            centroid_vec = np.array(self.centroid, dtype=np.float32)
            synapse.domain_similarity = float(centroid_vec @ query_emb)
        else:
            synapse.domain_similarity = 0.0

        synapse.node_id = self.node_id
        synapse.agent_uid = self.uid

        # If domain similarity is below threshold, enrich chunks with Unbrowse context
        if (
            synapse.query_text
            and synapse.query_text != "__corpus_challenge__"
            and (synapse.domain_similarity or 0.0) < UNBROWSE_CORPUS_THRESHOLD
        ):
            unbrowse_results = await self._unbrowse.fetch_context(
                query=synapse.query_text,
                node_id=self.node_id,
                max_results=2,
            )
            if unbrowse_results:
                if synapse.chunks is None:
                    synapse.chunks = []
                for r in unbrowse_results:
                    synapse.chunks.append({
                        "id": f"unbrowse:{r.url or 'web'}",
                        "text": r.content[:800],
                        "hash": "",
                        "score": r.confidence,
                        "char_start": 0,
                        "char_end": len(r.content),
                        "source": "unbrowse",
                    })
                log.info(
                    "Unbrowse fallback: added %d external chunks for node %s (sim=%.3f)",
                    len(unbrowse_results),
                    self.node_id,
                    synapse.domain_similarity,
                )

        return synapse

    async def _blacklist(self, synapse: KnowledgeQuery) -> tuple[bool, str]:
        hotkey = synapse.dendrite.hotkey
        if self.whitelist_hotkeys and hotkey in self.whitelist_hotkeys:
            return False, "Whitelisted"
        if hotkey not in self.metagraph.hotkeys:
            return True, "Hotkey not registered"
        uid = self.metagraph.hotkeys.index(hotkey)
        if not self.metagraph.validator_permit[uid]:
            return True, "No validator permit"
        return False, "Allowed"

    async def _priority(self, synapse: KnowledgeQuery) -> float:
        hotkey = synapse.dendrite.hotkey
        if hotkey not in self.metagraph.hotkeys:
            return 0.0
        uid = self.metagraph.hotkeys.index(hotkey)
        return float(self.metagraph.S[uid])

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self.axon.serve(netuid=NETUID, subtensor=self.subtensor)
        self.axon.start()
        log.info("Domain miner started on UID %d (node_id=%s)", self.uid, self.node_id)

    def stop(self) -> None:
        self.axon.stop()
        log.info("Domain miner stopped")

    def run_forever(self) -> None:
        """Start axon and block, resyncing metagraph every 60 s."""
        self.start()
        try:
            while True:
                self.metagraph.sync(subtensor=self.subtensor)
                time.sleep(60)
        except KeyboardInterrupt:
            self.stop()

    # Backward-compat alias
    def run(self) -> None:
        self.run_forever()

    # Exposed for validator challenge use
    def prove_chunk(self, chunk_index: int) -> dict:
        if self.merkle_prover is None:
            raise RuntimeError("No corpus loaded")
        return self.merkle_prover.prove(chunk_index)


if __name__ == "__main__":
    miner = DomainMiner()
    miner.run_forever()
