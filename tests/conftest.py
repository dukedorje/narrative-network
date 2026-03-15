"""Shared pytest fixtures for Narrative Network tests."""
import asyncio
import copy
import hashlib

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# FakeEmbedder — deterministic 768-dim vectors without SentenceTransformer
# ---------------------------------------------------------------------------


class FakeEmbedder:
    """Returns deterministic 768-dim vectors based on text hash. No model download."""

    def __init__(self, dim: int = 768):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

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

    def __init__(self, is_serving: bool = True, ip: str = "127.0.0.1", port: int = 8091):
        self.is_serving = is_serving
        self.ip = ip
        self.port = port


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
        self.axons = [MockAxonInfo(is_serving=s) for s in serving]

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

    Usage:
        dendrite = MockDendrite(wallet=mock_wallet)
        dendrite.register_handler(KnowledgeQuery, my_handler_fn)
        # my_handler_fn(synapse) -> synapse (mutated)
    """

    def __init__(self, wallet=None):
        self.wallet = wallet
        self._handlers: dict[type, callable] = {}
        self.call_log: list[dict] = []  # record all calls for assertions

    def register_handler(self, synapse_type: type, handler) -> None:
        """Register a handler function for a synapse type."""
        self._handlers[synapse_type] = handler

    async def __call__(self, axons, synapse, timeout=None, deserialize=False):
        """Route synapse to registered handler. Returns list of responses (one per axon)."""
        self.call_log.append(
            {
                "synapse_type": type(synapse).__name__,
                "axon_count": len(axons) if isinstance(axons, list) else 1,
            }
        )

        handler = self._handlers.get(type(synapse))
        if handler is None:
            # Return unmodified copies
            if isinstance(axons, list):
                return [synapse] * len(axons)
            return [synapse]

        results = []
        axon_list = axons if isinstance(axons, list) else [axons]
        for i, axon in enumerate(axon_list):
            syn_copy = copy.deepcopy(synapse)
            result = handler(syn_copy, axon_index=i)
            if asyncio.iscoroutine(result):
                result = await result
            results.append(result)

        return results

    # Sync version for non-async contexts
    def query(self, axons, synapse, timeout=None, deserialize=False):
        """Synchronous query — wraps async __call__."""
        return asyncio.get_event_loop().run_until_complete(
            self(axons, synapse, timeout=timeout, deserialize=deserialize)
        )


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_metagraph():
    """4-node metagraph: UID 0 = validator, UIDs 1-3 = miners."""
    return MockMetagraph(
        n=4,
        hotkeys=["validator-hotkey", "miner-1-hotkey", "miner-2-hotkey", "miner-3-hotkey"],
        stakes=[1000.0, 100.0, 100.0, 100.0],
        validator_permit=[True, False, False, False],
        axon_serving=[True, True, True, True],
    )


@pytest.fixture
def mock_wallet():
    """Wallet whose hotkey matches UID 0 (validator) in mock_metagraph."""
    return MockWallet(hotkey_address="validator-hotkey")


@pytest.fixture
def mock_subtensor(mock_metagraph):
    return MockSubtensor(metagraph=mock_metagraph)


@pytest.fixture
def mock_dendrite(mock_wallet):
    return MockDendrite(wallet=mock_wallet)


@pytest.fixture
def fake_embedder():
    return FakeEmbedder(dim=768)


@pytest.fixture
def graph_store():
    """In-memory GraphStore with no KuzuDB persistence."""
    from subnet.graph_store import GraphStore

    return GraphStore(db_path=None)
