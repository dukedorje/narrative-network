"""Integration tests for the Validator epoch loop with mock miners.

Exercises run_epoch() end-to-end: corpus challenge, traversal+quality scoring,
topology scoring, weight setting, and edge decay — all without real Bittensor.

Usage:
    uv run pytest tests/integration/test_validator_epoch.py -v
"""

import sys
import os

import pytest
import torch

# Root-level conftest classes are imported via sys.path; make sure tests/ is on path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from conftest import MockMetagraph, MockWallet, MockSubtensor, MockDendrite, MockMinerNetwork, FakeEmbedder

from subnet.graph_store import GraphStore
from subnet.config import EDGE_DECAY_RATE
from subnet.validator import Validator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def epoch_metagraph():
    """4-node metagraph: UID 0 = validator, UIDs 1-3 = miners (all serving)."""
    return MockMetagraph(
        n=4,
        hotkeys=["validator-hotkey", "miner-1-hotkey", "miner-2-hotkey", "miner-3-hotkey"],
        stakes=[1000.0, 100.0, 100.0, 100.0],
        validator_permit=[True, False, False, False],
        axon_serving=[True, True, True, True],
    )


@pytest.fixture
def epoch_wallet():
    """Wallet whose hotkey matches UID 0 in epoch_metagraph."""
    return MockWallet(hotkey_address="validator-hotkey")


@pytest.fixture
def epoch_graph_store():
    """In-memory GraphStore with triangle topology for UIDs 1-3."""
    gs = GraphStore(db_path=None)
    gs.add_node("node-1", state="Live")
    gs.add_node("node-2", state="Live")
    gs.add_node("node-3", state="Live")
    # Triangle: ensures non-zero betweenness centrality and outgoing edge weight sums.
    # Weight well above EDGE_DECAY_FLOOR (0.01) so decay is observable.
    gs.upsert_edge("node-1", "node-2", weight=1.0)
    gs.upsert_edge("node-2", "node-3", weight=1.0)
    gs.upsert_edge("node-3", "node-1", weight=1.0)
    return gs


@pytest.fixture
def validator(epoch_metagraph, epoch_wallet, epoch_graph_store):
    """Fully wired Validator with mock miners registered on the dendrite."""
    subtensor = MockSubtensor(metagraph=epoch_metagraph)
    dendrite = MockDendrite(wallet=epoch_wallet)
    embedder = FakeEmbedder(dim=768)

    MockMinerNetwork(
        n_miners=3,
        metagraph=epoch_metagraph,
        dendrite=dendrite,
        embedder=embedder,
        graph_node_ids=["node-1", "node-2", "node-3"],
    )

    return Validator(
        wallet=epoch_wallet,
        subtensor=subtensor,
        dendrite=dendrite,
        metagraph=epoch_metagraph,
        graph_store=epoch_graph_store,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_epoch_challenges_all_serving_miners(validator):
    """run_epoch issues KnowledgeQuery (corpus + regular) and NarrativeHop calls."""
    await validator.run_epoch()

    log = validator.dendrite.call_log
    synapse_types = [entry["synapse_type"] for entry in log]

    knowledge_query_calls = [t for t in synapse_types if t == "KnowledgeQuery"]
    narrative_hop_calls = [t for t in synapse_types if t == "NarrativeHop"]

    # Corpus challenge (1 batch to all miners) + regular query (1 batch to all miners)
    assert len(knowledge_query_calls) >= 2, (
        f"Expected at least 2 KnowledgeQuery calls, got {len(knowledge_query_calls)}"
    )
    # One NarrativeHop per challenged miner
    assert len(narrative_hop_calls) >= 1, (
        f"Expected at least 1 NarrativeHop call, got {len(narrative_hop_calls)}"
    )


async def test_epoch_sets_weights(validator):
    """run_epoch calls subtensor.set_weights exactly once with valid uids and weights."""
    await validator.run_epoch()

    calls = validator.subtensor.set_weights_calls
    assert len(calls) == 1, f"Expected 1 set_weights call, got {len(calls)}"

    call = calls[0]
    assert call["uids"] is not None, "uids must not be None"
    assert call["weights"] is not None, "weights must not be None"
    # Weights tensor must be same length as metagraph
    assert len(call["weights"]) == len(validator.metagraph.hotkeys), (
        "weights length must match metagraph size"
    )


async def test_epoch_scores_nonzero(validator):
    """run_epoch produces non-zero scores for at least one challenged miner (UIDs 1-3)."""
    await validator.run_epoch()

    miner_scores = validator.scores[1:4]  # UIDs 1, 2, 3
    assert miner_scores.sum().item() > 0.0, (
        f"Expected non-zero scores for miners 1-3, got {miner_scores}"
    )


async def test_epoch_decays_edges(validator, epoch_graph_store):
    """run_epoch decays all edges by EDGE_DECAY_RATE."""
    # Capture initial weights before the epoch
    initial_weights = {
        (e.source_id, e.dest_id): e.weight
        for e in epoch_graph_store.get_all_edges()
    }
    assert len(initial_weights) == 3, "Expected 3 triangle edges before epoch"

    await validator.run_epoch()

    for e in epoch_graph_store.get_all_edges():
        key = (e.source_id, e.dest_id)
        assert key in initial_weights, f"Unexpected edge {key} after epoch"
        expected = initial_weights[key] * EDGE_DECAY_RATE
        assert e.weight < initial_weights[key], (
            f"Edge {key} weight did not decrease: {initial_weights[key]} -> {e.weight}"
        )
        assert abs(e.weight - expected) < 1e-6, (
            f"Edge {key} weight mismatch: expected {expected:.6f}, got {e.weight:.6f}"
        )


async def test_epoch_no_miners_skips(epoch_wallet):
    """run_epoch with no serving miners increments step and returns without error."""
    no_serve_metagraph = MockMetagraph(
        n=4,
        hotkeys=["validator-hotkey", "miner-1-hotkey", "miner-2-hotkey", "miner-3-hotkey"],
        stakes=[1000.0, 100.0, 100.0, 100.0],
        validator_permit=[True, False, False, False],
        # Validator axon (UID 0) marked serving, miners not — validator excludes itself
        # so effective serving_uids will be empty.
        axon_serving=[True, False, False, False],
    )
    subtensor = MockSubtensor(metagraph=no_serve_metagraph)
    dendrite = MockDendrite(wallet=epoch_wallet)
    gs = GraphStore(db_path=None)

    v = Validator(
        wallet=epoch_wallet,
        subtensor=subtensor,
        dendrite=dendrite,
        metagraph=no_serve_metagraph,
        graph_store=gs,
    )

    assert v.step == 0
    await v.run_epoch()
    assert v.step == 1, "step must increment even when no miners are available"

    # No dendrite calls should have been made
    assert len(dendrite.call_log) == 0, (
        f"Expected no dendrite calls when no miners serve, got {dendrite.call_log}"
    )
    # No weights should have been set
    assert len(subtensor.set_weights_calls) == 0, (
        "set_weights must not be called when epoch is skipped"
    )
