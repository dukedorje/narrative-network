"""Unified miner — single process serving both KnowledgeQuery and NarrativeHop.

Merges DomainMiner (corpus retrieval + Merkle proofs) and NarrativeMiner
(LLM-driven hop generation via OpenRouter) into one Miner class with a
single axon, single UnbrowseClient, and shared Bittensor identity.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

import numpy as np

from subnet._bt_compat import _BT_AVAILABLE

if _BT_AVAILABLE:
    import bittensor as bt
else:
    bt = None  # type: ignore

from domain.corpus import Chunk, CorpusLoader, MerkleProver
from domain.narrative.prompt import build_prompt, fits_in_context
from domain.narrative.session_store import SessionStore
from subnet import NETUID
from subnet.config import (
    EMBEDDING_CACHE_DIR,
    EMBEDDING_MODEL,
    NARRATIVE_MAX_TOKENS,
    NARRATIVE_MODEL,
    NARRATIVE_TEMPERATURE,
    OPENROUTER_BASE_URL,
    UNBROWSE_CORPUS_THRESHOLD,
)

if _BT_AVAILABLE:
    from subnet.protocol import ChoiceCard, KnowledgeQuery, NarrativeHop
else:
    from subnet.protocol_local import ChoiceCard, KnowledgeQuery, NarrativeHop  # type: ignore

log = logging.getLogger(__name__)

_DEFAULT_REDIS_URL = os.environ.get("REDIS_URL", None)
_OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")


class Miner:
    """Unified miner: corpus retrieval, Merkle proofs, and LLM narrative generation.

    Attaches two forward handlers to a single axon:
    - KnowledgeQuery: semantic chunk retrieval with Merkle proof support
    - NarrativeHop: LLM-driven passage generation via OpenRouter

    Parameters
    ----------
    config:
        Optional bittensor config; defaults to bt.Config().
    corpus_dir:
        Directory containing corpus documents (.txt / .md).
    persona:
        Persona name from domain.narrative.prompt.PERSONAS.
    node_id:
        Logical node ID this miner serves.
    whitelist_hotkeys:
        Set of hotkeys always allowed through the blacklist.
    redis_url:
        Redis URL for session store; falls back to in-memory.
    """

    def __init__(
        self,
        config: "bt.Config | None" = None,
        corpus_dir: str | None = None,
        persona: str = "neutral",
        node_id: str | None = None,
        whitelist_hotkeys: list[str] | None = None,
        redis_url: str | None = _DEFAULT_REDIS_URL,
    ) -> None:
        if not _BT_AVAILABLE:
            raise ImportError("bittensor is required for production Miner")
        self.config = config or bt.Config()
        self.wallet = bt.Wallet(config=self.config)
        self.subtensor = bt.Subtensor(config=self.config)
        self.metagraph = self.subtensor.metagraph(NETUID)
        self.uid: int = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.node_id: str = node_id or f"node-{self.uid}"
        self.persona = persona
        self.whitelist_hotkeys: set[str] = set(whitelist_hotkeys or [])

        # -- Domain miner state: corpus + Merkle --
        self.chunks: list[Chunk] = []
        self.merkle_prover: MerkleProver | None = None
        self.corpus_root_hash: str = ""
        self.centroid: list[float] = []

        if corpus_dir:
            self._load_corpus(corpus_dir)

        # -- Narrative miner state: sessions + LLM client --
        self.session_store = SessionStore(redis_url=redis_url)
        self._client = None  # lazy-init AsyncOpenAI

        if not _OPENROUTER_API_KEY:
            log.warning(
                "OPENROUTER_API_KEY not set — NarrativeHop will return empty passages. "
                "Set the env var to enable LLM generation."
            )

        # -- Shared --
        from orchestrator.unbrowse import UnbrowseClient

        self._unbrowse = UnbrowseClient()

        # -- Axon with two forward handlers --
        self.axon = bt.Axon(wallet=self.wallet, config=self.config)
        self.axon.attach(
            forward_fn=self._forward_kq,
            blacklist_fn=self._blacklist_kq,
            priority_fn=self._priority_kq,
        )
        self.axon.attach(
            forward_fn=self._forward_nh,
            blacklist_fn=self._blacklist_nh,
            priority_fn=self._priority_nh,
        )

    # ------------------------------------------------------------------
    # Corpus loading
    # ------------------------------------------------------------------

    def _load_corpus(self, corpus_dir: str) -> None:
        log.info("Loading corpus from %s", corpus_dir)
        cache_dir = Path(EMBEDDING_CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_name = Path(corpus_dir).name or "corpus"
        loader = CorpusLoader(
            corpus_dir=corpus_dir,
            model_name=EMBEDDING_MODEL,
            cache_path=cache_dir / f"{cache_name}.pkl",
        )
        self.chunks = loader.load()
        self.centroid = loader.centroid
        self.merkle_prover = MerkleProver(self.chunks)
        self.corpus_root_hash = self.merkle_prover.root
        log.info(
            "Corpus loaded: %d chunks, root=%s\u2026",
            len(self.chunks),
            self.corpus_root_hash[:16],
        )

    # ------------------------------------------------------------------
    # OpenRouter client (lazy)
    # ------------------------------------------------------------------

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI  # type: ignore

            self._client = AsyncOpenAI(
                api_key=_OPENROUTER_API_KEY or "sk-placeholder",
                base_url=OPENROUTER_BASE_URL,
            )
        return self._client

    # ------------------------------------------------------------------
    # LLM generation
    # ------------------------------------------------------------------

    async def _generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> dict | None:
        """Call OpenRouter and parse JSON response. Returns None on failure."""
        client = self._get_client()
        try:
            response = await client.chat.completions.create(
                model=NARRATIVE_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=NARRATIVE_MAX_TOKENS,
                temperature=NARRATIVE_TEMPERATURE,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("Miner: JSON parse error: %s", exc)
            return None
        except Exception as exc:
            log.error("Miner: generation error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _update_session(self, session_id: str, passage: str) -> None:
        """Append the latest passage to session history."""
        history: list[str] = await self.session_store.get_field(session_id, "history", default=[])
        history.append(passage)
        await self.session_store.update_field(session_id, "history", history)

    # ------------------------------------------------------------------
    # KnowledgeQuery handlers
    # ------------------------------------------------------------------

    async def _forward_kq(self, synapse: KnowledgeQuery) -> KnowledgeQuery:
        """Handle KnowledgeQuery -- chunk retrieval or corpus challenge."""
        if synapse.query_text == "__corpus_challenge__":
            if self.merkle_prover and self.chunks:
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
                    synapse.chunks.append(
                        {
                            "id": f"unbrowse:{r.url or 'web'}",
                            "text": r.content[:800],
                            "hash": "",
                            "score": r.confidence,
                            "char_start": 0,
                            "char_end": len(r.content),
                            "source": "unbrowse",
                        }
                    )
                log.info(
                    "Unbrowse fallback: added %d external chunks for node %s (sim=%.3f)",
                    len(unbrowse_results),
                    self.node_id,
                    synapse.domain_similarity,
                )

        return synapse

    async def _blacklist_kq(self, synapse: KnowledgeQuery) -> tuple[bool, str]:
        hotkey = synapse.dendrite.hotkey
        if self.whitelist_hotkeys and hotkey in self.whitelist_hotkeys:
            return False, "Whitelisted"
        if hotkey not in self.metagraph.hotkeys:
            return True, "Hotkey not registered"
        uid = self.metagraph.hotkeys.index(hotkey)
        if not self.metagraph.validator_permit[uid]:
            return True, "No validator permit"
        return False, "Allowed"

    async def _priority_kq(self, synapse: KnowledgeQuery) -> float:
        hotkey = synapse.dendrite.hotkey
        if hotkey not in self.metagraph.hotkeys:
            return 0.0
        uid = self.metagraph.hotkeys.index(hotkey)
        return float(self.metagraph.S[uid])

    # ------------------------------------------------------------------
    # NarrativeHop handlers
    # ------------------------------------------------------------------

    async def _forward_nh(self, synapse: NarrativeHop) -> NarrativeHop:
        """Handle NarrativeHop -- LLM-driven passage generation."""
        # If no API key, return empty passage gracefully
        if not _OPENROUTER_API_KEY:
            synapse.narrative_passage = ""
            synapse.choice_cards = []
            synapse.knowledge_synthesis = ""
            synapse.agent_uid = self.uid
            return synapse

        # Enrich hop generation with live external context not in the graph
        unbrowse_context = ""
        if synapse.destination_node_id:
            unbrowse_results = await self._unbrowse.fetch_context(
                query=synapse.prior_narrative or synapse.destination_node_id,
                node_id=synapse.destination_node_id,
                max_results=2,
            )
            unbrowse_context = self._unbrowse.format_for_prompt(unbrowse_results)

        augmented_chunks = list(synapse.retrieved_chunks or [])
        if unbrowse_context:
            augmented_chunks.append({"text": unbrowse_context, "id": "unbrowse:live", "score": 0.5})

        system_prompt, user_prompt = build_prompt(
            destination_node_id=synapse.destination_node_id,
            player_path=synapse.player_path,
            prior_narrative=synapse.prior_narrative,
            retrieved_chunks=augmented_chunks,
            persona=self.persona,
            num_choices=3,
        )

        if not fits_in_context(system_prompt, user_prompt, max_tokens=8192):
            log.warning("Prompt may exceed context window for session %s", synapse.session_id)

        result = await self._generate(system_prompt, user_prompt)

        if result is None:
            synapse.narrative_passage = "(generation failed)"
            synapse.choice_cards = []
            synapse.knowledge_synthesis = ""
            synapse.agent_uid = self.uid
            return synapse

        synapse.narrative_passage = result.get("narrative_passage", "")
        synapse.knowledge_synthesis = result.get("knowledge_synthesis", "")

        raw_cards = result.get("choice_cards", [])
        synapse.choice_cards = []
        for card in raw_cards:
            if isinstance(card, dict):
                try:
                    synapse.choice_cards.append(
                        ChoiceCard(
                            text=card.get("text", ""),
                            destination_node_id=card.get("destination_node_id", ""),
                            edge_weight_delta=float(card.get("edge_weight_delta", 0.0)),
                            thematic_color=card.get("thematic_color", "#888888"),
                        )
                    )
                except Exception as exc:
                    log.warning("Skipping malformed choice card: %s", exc)

        synapse.agent_uid = self.uid

        if synapse.session_id and synapse.narrative_passage:
            asyncio.create_task(self._update_session(synapse.session_id, synapse.narrative_passage))

        return synapse

    async def _blacklist_nh(self, synapse: NarrativeHop) -> tuple[bool, str]:
        hotkey = synapse.dendrite.hotkey
        if self.whitelist_hotkeys and hotkey in self.whitelist_hotkeys:
            return False, "Whitelisted"
        if hotkey not in self.metagraph.hotkeys:
            return True, "Hotkey not registered"
        uid = self.metagraph.hotkeys.index(hotkey)
        if not self.metagraph.validator_permit[uid]:
            return True, "No validator permit"
        return False, "Allowed"

    async def _priority_nh(self, synapse: NarrativeHop) -> float:
        hotkey = synapse.dendrite.hotkey
        if hotkey not in self.metagraph.hotkeys:
            return 0.0
        uid = self.metagraph.hotkeys.index(hotkey)
        return float(self.metagraph.S[uid])

    # ------------------------------------------------------------------
    # Exposed for validator challenge use
    # ------------------------------------------------------------------

    def prove_chunk(self, chunk_index: int) -> dict:
        if self.merkle_prover is None:
            raise RuntimeError("No corpus loaded")
        return self.merkle_prover.prove(chunk_index)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        asyncio.get_event_loop().run_until_complete(self.session_store.connect())
        self.axon.serve(netuid=NETUID, subtensor=self.subtensor)
        self.axon.start()
        log.info(
            "Unified miner started on UID %d (node_id=%s, persona=%s)",
            self.uid,
            self.node_id,
            self.persona,
        )

    def stop(self) -> None:
        self.axon.stop()
        asyncio.get_event_loop().run_until_complete(self.session_store.close())
        log.info("Unified miner stopped")

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


class LocalMiner:
    """Unified miner stub for local/demo mode.

    In local mode, the gateway runs corpus retrieval and narrative generation
    in-process. This stub keeps the K8s pod alive and healthy.
    """

    def __init__(self) -> None:
        self.log = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)

        self.log.info("Unified miner starting in local/demo mode")
        self.log.info("Corpus retrieval and narrative generation handled by gateway")

        # Verify seed topology is accessible
        from seed.loader import load_topology

        graph_store, corpus_map = load_topology()
        total_chunks = sum(len(files) for files in corpus_map.values())
        self.log.info(
            "Seed topology verified: %d nodes, %d corpus files",
            graph_store.stats()["node_count"],
            total_chunks,
        )

        if not os.environ.get("OPENROUTER_API_KEY"):
            self.log.warning(
                "OPENROUTER_API_KEY not set -- gateway generation will use placeholder"
            )
        else:
            self.log.info("OpenRouter API key configured")

    def run_forever(self) -> None:
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok","mode":"local","type":"unified"}')

            def log_message(self, format, *args):  # noqa: A002
                pass  # Suppress request logs

        server = HTTPServer(("0.0.0.0", 8091), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.log.info("Health server listening on :8091")

        self.log.info("Local unified miner idle -- gateway handles all requests")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            server.shutdown()
            self.log.info("Local unified miner stopped")


if __name__ == "__main__":
    if os.environ.get("AXON_NETWORK") == "local":
        miner: Miner | LocalMiner = LocalMiner()
    else:
        miner = Miner()
    miner.run_forever()
