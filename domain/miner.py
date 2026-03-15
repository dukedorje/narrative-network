"""Domain miner — serves corpus chunks and Merkle proofs.

One instance per registered node ID. Handles KnowledgeQuery synapses.
"""

from __future__ import annotations

import bittensor as bt

from subnet import NETUID
from subnet.protocol import KnowledgeQuery


class DomainMiner:
    """Domain miner: corpus retrieval and Merkle proof service."""

    def __init__(self, config: bt.config | None = None):
        self.config = config or bt.config()
        self.wallet = bt.Wallet(config=self.config)
        self.subtensor = bt.Subtensor(config=self.config)
        self.metagraph = self.subtensor.metagraph(NETUID)
        self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)

        # TODO: Initialize Chroma vector store
        # TODO: Load corpus and compute Merkle tree
        # TODO: Compute centroid embedding

        self.axon = bt.Axon(wallet=self.wallet, config=self.config)
        self.axon.attach(
            forward_fn=self.forward,
            blacklist_fn=self.blacklist,
            priority_fn=self.priority,
        )

    async def forward(self, synapse: KnowledgeQuery) -> KnowledgeQuery:
        """Handle KnowledgeQuery — chunk retrieval or corpus challenge."""
        if synapse.query_text == "__corpus_challenge__":
            # TODO: Return Merkle proof for integrity check
            return synapse

        # TODO: Query Chroma vector store
        # synapse.chunks = results
        # synapse.domain_similarity = similarity
        # synapse.node_id = self.node_id
        # synapse.agent_uid = self.uid
        return synapse

    async def blacklist(self, synapse: KnowledgeQuery) -> tuple[bool, str]:
        if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
            return True, "Hotkey not registered"
        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        if not self.metagraph.validator_permit[uid]:
            return True, "No validator permit"
        return False, "Allowed"

    async def priority(self, synapse: KnowledgeQuery) -> float:
        uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
        return float(self.metagraph.S[uid])

    def run(self) -> None:
        self.axon.serve(netuid=NETUID, subtensor=self.subtensor)
        self.axon.start()
        bt.logging.info(f"Domain miner running on UID {self.uid}")

        import time

        while True:
            self.metagraph.sync(subtensor=self.subtensor)
            time.sleep(60)


if __name__ == "__main__":
    miner = DomainMiner()
    miner.run()
