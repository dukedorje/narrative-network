"""Narrative miner — LLM-driven hop generation via OpenRouter.

Handles NarrativeHop synapses using an async OpenAI-compatible client
pointed at OpenRouter.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import bittensor as bt

from subnet import NETUID
from subnet.config import (
    NARRATIVE_MAX_TOKENS,
    NARRATIVE_MODEL,
    NARRATIVE_TEMPERATURE,
    OPENROUTER_BASE_URL,
    SubnetConfig,
)
from subnet.protocol import NarrativeHop, ChoiceCard
from domain.narrative.prompt import build_prompt, fits_in_context
from domain.narrative.session_store import SessionStore

log = logging.getLogger(__name__)

_DEFAULT_REDIS_URL = os.environ.get("REDIS_URL", None)
_OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")


class NarrativeMiner:
    """Narrative miner: LLM-driven passage generation and choice curation.

    Parameters
    ----------
    config:
        Optional bittensor config; defaults to bt.Config().
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
        config: bt.Config | None = None,
        persona: str = "neutral",
        node_id: str | None = None,
        whitelist_hotkeys: list[str] | None = None,
        redis_url: str | None = _DEFAULT_REDIS_URL,
    ) -> None:
        self.config = config or bt.Config()
        self.wallet = bt.Wallet(config=self.config)
        self.subtensor = bt.Subtensor(config=self.config)
        self.metagraph = self.subtensor.metagraph(NETUID)
        self.uid: int = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.node_id: str = node_id or f"node-{self.uid}"
        self.persona = persona
        self.whitelist_hotkeys: set[str] = set(whitelist_hotkeys or [])

        self.session_store = SessionStore(redis_url=redis_url)

        self._client = None  # lazy-init AsyncOpenAI

        from orchestrator.unbrowse import UnbrowseClient
        self._unbrowse = UnbrowseClient()

        self.axon = bt.Axon(wallet=self.wallet, config=self.config)
        self.axon.attach(
            forward_fn=self._forward,
            blacklist_fn=self._blacklist,
            priority_fn=self._priority,
        )

    # ------------------------------------------------------------------
    # OpenRouter client
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
            log.warning("NarrativeMiner: JSON parse error: %s", exc)
            return None
        except Exception as exc:
            log.error("NarrativeMiner: generation error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _update_session(self, session_id: str, passage: str) -> None:
        """Append the latest passage to session history."""
        history: list[str] = await self.session_store.get_field(
            session_id, "history", default=[]
        )
        history.append(passage)
        await self.session_store.update_field(session_id, "history", history)

    # ------------------------------------------------------------------
    # Axon handlers
    # ------------------------------------------------------------------

    async def _forward(self, synapse: NarrativeHop) -> NarrativeHop:
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
            asyncio.create_task(
                self._update_session(synapse.session_id, synapse.narrative_passage)
            )

        return synapse

    async def _blacklist(self, synapse: NarrativeHop) -> tuple[bool, str]:
        hotkey = synapse.dendrite.hotkey
        if self.whitelist_hotkeys and hotkey in self.whitelist_hotkeys:
            return False, "Whitelisted"
        if hotkey not in self.metagraph.hotkeys:
            return True, "Hotkey not registered"
        uid = self.metagraph.hotkeys.index(hotkey)
        if not self.metagraph.validator_permit[uid]:
            return True, "No validator permit"
        return False, "Allowed"

    async def _priority(self, synapse: NarrativeHop) -> float:
        hotkey = synapse.dendrite.hotkey
        if hotkey not in self.metagraph.hotkeys:
            return 0.0
        uid = self.metagraph.hotkeys.index(hotkey)
        return float(self.metagraph.S[uid])

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _setup(self) -> None:
        await self.session_store.connect()

    def start(self) -> None:
        asyncio.get_event_loop().run_until_complete(self._setup())
        self.axon.serve(netuid=NETUID, subtensor=self.subtensor)
        self.axon.start()
        log.info("Narrative miner started on UID %d (node_id=%s)", self.uid, self.node_id)

    def stop(self) -> None:
        self.axon.stop()
        asyncio.get_event_loop().run_until_complete(self.session_store.close())
        log.info("Narrative miner stopped")

    def run_forever(self) -> None:
        """Start axon and block, resyncing metagraph every 60 s."""
        self.start()
        try:
            while True:
                self.metagraph.sync(subtensor=self.subtensor)
                time.sleep(60)
        except KeyboardInterrupt:
            self.stop()


if __name__ == "__main__":
    miner = NarrativeMiner()
    miner.run_forever()
