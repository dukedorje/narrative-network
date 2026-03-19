"""Shared pytest fixtures for Bittensor Knowledge Network tests."""
import pytest

from subnet.harness import (
    FakeEmbedder,
    MockAxonInfo,
    MockDendrite,
    MockHotkey,
    MockMetagraph,
    MockMinerNetwork,
    MockSubtensor,
    MockWallet,
    SetWeightsResponse,
)

__all__ = [
    "FakeEmbedder",
    "MockAxonInfo",
    "MockDendrite",
    "MockHotkey",
    "MockMetagraph",
    "MockMinerNetwork",
    "MockSubtensor",
    "MockWallet",
    "SetWeightsResponse",
]


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


@pytest.fixture
def mock_miner_network(mock_metagraph, mock_dendrite, fake_embedder):
    """MockMinerNetwork with 3 miners wired to mock_dendrite."""
    return MockMinerNetwork(
        n_miners=3,
        metagraph=mock_metagraph,
        dendrite=mock_dendrite,
        embedder=fake_embedder,
    )
