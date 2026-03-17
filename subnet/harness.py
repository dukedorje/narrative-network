"""Reusable offline harness for Narrative Network.

Provides mock Bittensor infrastructure (metagraph, wallet, subtensor, dendrite)
that can be used by tests, local dev mode, and offline validation.
No bittensor dependency required.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib

import numpy as np

from subnet._bt_compat import _BT_AVAILABLE

# ---------------------------------------------------------------------------
# FakeEmbedder — deterministic 768-dim vectors without SentenceTransformer
# ---------------------------------------------------------------------------


class FakeEmbedder:
    """Returns deterministic 768-dim vectors based on text hash. No model download."""

    def __init__(self, dim: int = 768):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        return self._hash_embed(text)

    def _hash_embed(self, text: str) -> list[float]:
        """Generate a deterministic unit vector from text hash."""
        h = hashlib.sha256(text.encode()).digest()
        # Use hash bytes as seed for reproducible random vector
        rng = np.random.RandomState(int.from_bytes(h[:4], "big"))
        vec = rng.randn(self.dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


# ---------------------------------------------------------------------------
# MockMetagraph
# ---------------------------------------------------------------------------


class MockAxonInfo:
    """Minimal axon info for metagraph."""

    def __init__(
        self, is_serving: bool = True, ip: str = "127.0.0.1", port: int = 8091, uid: int = 0,
    ):
        self.is_serving = is_serving
        self.ip = ip
        self.port = port
        self.uid = uid


class MockMetagraph:
    """Configurable metagraph mock with hotkeys, UIDs, stakes, and validator permits."""

    def __init__(
        self,
        n: int = 4,  # 1 validator + 3 miners
        hotkeys: list[str] | None = None,
        stakes: list[float] | None = None,
        validator_permit: list[bool] | None = None,
        axon_serving: list[bool] | None = None,
    ):
        self.n = n
        self.hotkeys = hotkeys or [f"hotkey-{i}" for i in range(n)]
        self.uids = list(range(n))
        self.S = stakes or [100.0] * n  # stake per UID
        self.validator_permit = validator_permit or ([True] + [False] * (n - 1))

        serving = axon_serving or [True] * n
        self.axons = [MockAxonInfo(is_serving=s, uid=i) for i, s in enumerate(serving)]

    def sync(self, subtensor=None) -> None:
        """No-op sync."""
        pass


# ---------------------------------------------------------------------------
# MockWallet
# ---------------------------------------------------------------------------


class MockHotkey:
    def __init__(self, ss58_address: str):
        self.ss58_address = ss58_address


class MockWallet:
    """Minimal wallet with configurable hotkey address."""

    def __init__(self, hotkey_address: str = "hotkey-0"):
        self.hotkey = MockHotkey(ss58_address=hotkey_address)
        self.name = "test-wallet"
        self.hotkey_str = hotkey_address


# ---------------------------------------------------------------------------
# MockSubtensor
# ---------------------------------------------------------------------------


class SetWeightsResponse:
    """Response object matching what subtensor.set_weights() returns."""

    def __init__(self, success: bool = True, message: str = "ok"):
        self.success = success
        self.message = message


class MockSubtensor:
    """Mock subtensor that returns configurable metagraph and accepts set_weights."""

    def __init__(self, metagraph: MockMetagraph | None = None):
        self._metagraph = metagraph or MockMetagraph()
        self.set_weights_calls: list[dict] = []  # record calls for assertions
        self._commitments: dict[tuple[int, int], str] = {}  # (netuid, uid) -> data

    def get_commitment(self, netuid: int, uid: int, block: int | None = None) -> str | None:
        """Retrieve a commitment stored by a miner. Returns None if not found."""
        return self._commitments.get((netuid, uid))

    def set_commitment(self, netuid: int, uid: int, data: str) -> None:
        """Store a commitment for a miner (used by tests to simulate manifest publication)."""
        self._commitments[(netuid, uid)] = data

    def metagraph(self, netuid: int) -> MockMetagraph:
        return self._metagraph

    def set_weights(
        self,
        wallet=None,
        netuid=None,
        uids=None,
        weights=None,
        mechid=None,
        wait_for_inclusion=None,
    ) -> SetWeightsResponse:
        self.set_weights_calls.append(
            {
                "netuid": netuid,
                "uids": uids,
                "weights": weights,
                "mechid": mechid,
            }
        )
        return SetWeightsResponse(success=True, message="ok")


# ---------------------------------------------------------------------------
# MockDendrite
# ---------------------------------------------------------------------------


class MockDendrite:
    """Mock dendrite that routes synapses to registered handler functions.

    Supports per-UID handler routing: register_handler(SynapseType, handler, uid=N).
    When uid is None, the handler is a fallback for all axons of that synapse type.
    When uid is set, only the axon at that UID gets that handler.

    Usage:
        dendrite = MockDendrite(wallet=mock_wallet)
        dendrite.register_handler(KnowledgeQuery, my_handler_fn)
        dendrite.register_handler(KnowledgeQuery, special_handler, uid=2)
    """

    def __init__(self, wallet=None):
        self.wallet = wallet
        self._handlers: dict[type, callable] = {}
        self._uid_handlers: dict[tuple[type, int], callable] = {}
        self.call_log: list[dict] = []  # record all calls for assertions

    def register_handler(self, synapse_type: type, handler, uid: int | None = None) -> None:
        """Register a handler function for a synapse type, optionally per-UID."""
        if uid is not None:
            self._uid_handlers[(synapse_type, uid)] = handler
        else:
            self._handlers[synapse_type] = handler

    async def __call__(self, axons, synapse, timeout=None, deserialize=False):
        """Route synapse to registered handler. Returns list of responses (one per axon)."""
        axon_list = axons if isinstance(axons, list) else [axons]
        self.call_log.append(
            {
                "synapse_type": type(synapse).__name__,
                "axon_count": len(axon_list),
                "axon_uids": [getattr(a, "uid", None) for a in axon_list],
            }
        )

        fallback_handler = self._handlers.get(type(synapse))

        results = []
        for i, axon in enumerate(axon_list):
            axon_uid = getattr(axon, "uid", i)
            # Check for UID-specific handler first, then fallback
            handler = self._uid_handlers.get((type(synapse), axon_uid), fallback_handler)

            syn_copy = copy.deepcopy(synapse)
            if handler is not None:
                try:
                    result = handler(syn_copy, axon_index=i, axon_uid=axon_uid)
                except TypeError:
                    # Backward compat: handler may not accept axon_uid
                    result = handler(syn_copy, axon_index=i)
                if asyncio.iscoroutine(result):
                    result = await result
                results.append(result)
            else:
                results.append(syn_copy)

        return results

    # Sync version for non-async contexts
    def query(self, axons, synapse, timeout=None, deserialize=False):
        """Synchronous query — wraps async __call__."""
        return asyncio.get_event_loop().run_until_complete(
            self(axons, synapse, timeout=timeout, deserialize=deserialize)
        )


# ---------------------------------------------------------------------------
# MockMinerNetwork — wires up N domain + N narrative mock miners
# ---------------------------------------------------------------------------


class MockMinerNetwork:
    """Creates N mock domain and narrative miner handlers, registers them on a MockDendrite.

    Domain miner handlers respond to KnowledgeQuery with chunks, domain_similarity,
    node_id, and merkle_proof.

    Narrative miner handlers respond to NarrativeHop with narrative_passage (30+ words),
    choice_cards, knowledge_synthesis, and passage_embedding.

    Usage:
        network = MockMinerNetwork(n_miners=3, metagraph=mock_metagraph, dendrite=mock_dendrite)
        # dendrite now has handlers registered for KnowledgeQuery and NarrativeHop
    """

    def __init__(
        self,
        n_miners: int = 3,
        metagraph: MockMetagraph | None = None,
        dendrite: MockDendrite | None = None,
        embedder: FakeEmbedder | None = None,
        graph_node_ids: list[str] | None = None,
    ):
        self.n_miners = n_miners
        self.metagraph = metagraph
        self.dendrite = dendrite
        self._embedder = embedder or FakeEmbedder(dim=768)
        self._node_ids = graph_node_ids or [f"node-{i}" for i in range(n_miners)]

        if dendrite is not None:
            self._register_handlers()

    def _register_handlers(self) -> None:
        if _BT_AVAILABLE:
            from subnet.protocol import KnowledgeQuery, NarrativeHop
        else:
            from subnet.protocol_local import KnowledgeQuery, NarrativeHop  # type: ignore[no-redef]

        self.dendrite.register_handler(KnowledgeQuery, self._domain_handler)
        self.dendrite.register_handler(NarrativeHop, self._narrative_handler)

    def _domain_handler(self, synapse, axon_index: int = 0, axon_uid: int = 0):
        """Handle KnowledgeQuery — return chunks, similarity, node_id, merkle_proof."""
        # Map axon to a node_id
        node_id = self._node_ids[axon_index % len(self._node_ids)]

        # Corpus challenge response
        if synapse.query_text == "__corpus_challenge__":
            synapse.merkle_proof = {
                "leaf_hash": "abc123",
                "siblings": ["def456", "ghi789"],
                "root": "root_hash_001",
            }
            synapse.node_id = node_id
            return synapse

        # Normal knowledge query
        chunk_texts = [
            f"Knowledge chunk {i} from {node_id}: This covers important concepts "
            f"in the domain of {node_id.replace('-', ' ')} with detailed analysis."
            for i in range(min(synapse.top_k, 3))
        ]
        synapse.chunks = [
            {
                "text": text,
                "hash": hashlib.sha256(text.encode()).hexdigest(),
                "score": 0.9 - (i * 0.1),
            }
            for i, text in enumerate(chunk_texts)
        ]
        synapse.domain_similarity = 0.85 - (axon_index * 0.05)
        synapse.node_id = node_id
        synapse.merkle_proof = {
            "leaf_hash": hashlib.sha256(chunk_texts[0].encode()).hexdigest(),
            "siblings": ["sib1", "sib2"],
            "root": "root_hash_001",
        }
        return synapse

    def _narrative_handler(self, synapse, axon_index: int = 0, axon_uid: int = 0):
        """Handle NarrativeHop — return passage (30+ words), choice_cards, embedding."""
        if _BT_AVAILABLE:
            from subnet.protocol import ChoiceCard
        else:
            from subnet.protocol_local import ChoiceCard  # type: ignore[no-redef]

        dest = synapse.destination_node_id
        passage_words = (
            f"You step into the domain of {dest.replace('-', ' ')}. "
            f"The knowledge here weaves through interconnected concepts that build upon "
            f"your previous explorations. Each pathway reveals new understanding, connecting "
            f"theoretical foundations with practical applications. The landscape of ideas "
            f"stretches before you, rich with possibility and discovery. Ancient wisdom "
            f"meets modern insight in this remarkable intellectual territory."
        )
        synapse.narrative_passage = passage_words

        # Generate choice cards pointing to adjacent nodes
        adjacent = [nid for nid in self._node_ids if nid != dest][:3]
        synapse.choice_cards = [
            ChoiceCard(
                text=f"Explore {nid.replace('-', ' ')}",
                destination_node_id=nid,
                edge_weight_delta=0.1,
                thematic_color="#6ee7b7",
            )
            for nid in adjacent
        ]

        synapse.knowledge_synthesis = f"Synthesis of {dest}: bridging concepts across domains."
        synapse.passage_embedding = self._embedder.embed_one(passage_words)
        return synapse

    def domain_handler(self, uid: int):
        """Return the domain handler function for a specific UID."""
        def handler(synapse, axon_index=0, axon_uid=0):
            return self._domain_handler(synapse, axon_index=uid, axon_uid=uid)
        return handler

    def narrative_handler(self, uid: int):
        """Return the narrative handler function for a specific UID."""
        def handler(synapse, axon_index=0, axon_uid=0):
            return self._narrative_handler(synapse, axon_index=uid, axon_uid=uid)
        return handler


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_local_network(
    n_miners: int = 3,
    graph_node_ids: list[str] | None = None,
) -> dict:
    """Create a fully-wired local network for offline operation.

    Returns dict with keys: metagraph, wallet, subtensor, dendrite,
    miner_network, embedder — ready to inject into LocalValidator, Gateway, etc.
    """
    metagraph = MockMetagraph(
        n=n_miners + 1,  # +1 for validator at UID 0
        hotkeys=["validator-hotkey"] + [f"miner-{i}-hotkey" for i in range(n_miners)],
        stakes=[1000.0] + [100.0] * n_miners,
        validator_permit=[True] + [False] * n_miners,
    )
    wallet = MockWallet(hotkey_address="validator-hotkey")
    subtensor = MockSubtensor(metagraph=metagraph)
    dendrite = MockDendrite(wallet=wallet)
    embedder = FakeEmbedder(dim=768)
    miner_network = MockMinerNetwork(
        n_miners=n_miners,
        metagraph=metagraph,
        dendrite=dendrite,
        embedder=embedder,
        graph_node_ids=graph_node_ids,
    )
    return {
        "metagraph": metagraph,
        "wallet": wallet,
        "subtensor": subtensor,
        "dendrite": dendrite,
        "miner_network": miner_network,
        "embedder": embedder,
    }
