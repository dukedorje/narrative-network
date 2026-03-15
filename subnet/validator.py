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

    def __init__(self, config: bt.config | None = None):
        self.config = config or bt.config()
        self.wallet = bt.Wallet(config=self.config)
        self.subtensor = bt.Subtensor(config=self.config)
        self.metagraph = self.subtensor.metagraph(NETUID)
        self.dendrite = bt.Dendrite(wallet=self.wallet)

        self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.hotkeys = copy(self.metagraph.hotkeys)
        self.scores = torch.zeros(len(self.metagraph.hotkeys))
        self.step = 0

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
        self.resync_metagraph()

        # TODO: Implement full scoring loop
        # 1. Sample recently-completed sessions from graph store
        # 2. Replay NarrativeHop challenges to miners
        # 3. Score on four axes
        # 4. Run corpus challenges
        # 5. Compute topology scores
        bt.logging.info(f"Epoch {self.step}: scoring {len(self.metagraph.uids)} UIDs")

        self.set_weights()
        # TODO: graph_store.decay_edges()
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
