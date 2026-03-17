"""Unit tests for subnet.validator.Validator using mock dependencies."""

import pytest
import torch

from subnet.protocol import KnowledgeQuery, NarrativeHop
from subnet.validator import Validator
from tests.conftest import FakeEmbedder

# ---------------------------------------------------------------------------
# Helpers — register standard handlers on mock_dendrite
# ---------------------------------------------------------------------------


def _register_handlers(mock_dendrite):
    def kq_handler(synapse, axon_index=0):
        if synapse.query_text == "__corpus_challenge__":
            synapse.merkle_proof = {
                "leaf_index": 0,
                "leaf_hash": "a" * 64,
                "siblings": [{"hash": "b" * 64, "position": "right"}],
                "root": "c" * 64,
            }
        else:
            synapse.chunks = [
                {
                    "id": "chunk-0",
                    "text": "quantum test",
                    "hash": "d" * 64,
                    "score": 0.9,
                }
            ]
            synapse.domain_similarity = 0.8
            synapse.node_id = f"node-{axon_index + 1}"
        synapse.agent_uid = axon_index + 1
        return synapse

    def nh_handler(synapse, axon_index=0):
        synapse.narrative_passage = " ".join(["quantum"] * 200)
        synapse.passage_embedding = [1.0] + [0.0] * 767
        synapse.choice_cards = []
        synapse.agent_uid = axon_index + 1
        return synapse

    mock_dendrite.register_handler(KnowledgeQuery, kq_handler)
    mock_dendrite.register_handler(NarrativeHop, nh_handler)


def _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store):
    return Validator(
        config=None,
        wallet=mock_wallet,
        subtensor=mock_subtensor,
        dendrite=mock_dendrite,
        metagraph=mock_metagraph,
        graph_store=graph_store,
        embedder=FakeEmbedder(dim=768),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_validator_init_with_mocks(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """Validator can be instantiated without touching a real BT chain."""
    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    assert v is not None
    assert v.step == 0
    assert len(v.scores) == 4


def test_validator_uid_correct(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """Validator UID matches the position of the wallet hotkey in the metagraph."""
    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    # validator-hotkey is at index 0
    assert v.uid == 0


def test_resync_metagraph_no_change(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """Resync with unchanged hotkeys preserves existing scores."""
    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    v.scores = torch.tensor([0.0, 0.5, 0.3, 0.2])
    v.resync_metagraph()
    assert float(v.scores[1]) == pytest.approx(0.5)
    assert float(v.scores[2]) == pytest.approx(0.3)


def test_resync_metagraph_hotkey_swap(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """If a hotkey changes, that UID's score is reset to 0."""
    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    v.scores = torch.tensor([0.0, 0.9, 0.3, 0.1])

    # Swap hotkey at UID 1
    mock_metagraph.hotkeys[1] = "new-miner-hotkey"
    v.resync_metagraph()

    assert float(v.scores[1]) == pytest.approx(0.0)
    # Other scores unchanged
    assert float(v.scores[2]) == pytest.approx(0.3)


def test_resync_metagraph_growth(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """When metagraph grows, score tensor resizes and preserves existing values."""
    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    v.scores = torch.tensor([0.0, 0.4, 0.3, 0.2])

    # Expand metagraph by one UID
    mock_metagraph.hotkeys.append("new-miner-5-hotkey")
    mock_metagraph.n = 5
    mock_metagraph.uids = list(range(5))
    mock_metagraph.S.append(100.0)
    mock_metagraph.validator_permit.append(False)
    from tests.conftest import MockAxonInfo
    mock_metagraph.axons.append(MockAxonInfo(is_serving=True))

    v.resync_metagraph()

    assert len(v.scores) == 5
    assert float(v.scores[1]) == pytest.approx(0.4)
    assert float(v.scores[4]) == pytest.approx(0.0)


def test_update_scores_basic(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """Moving average update changes scores correctly."""
    from subnet.config import MOVING_AVERAGE_ALPHA

    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    v.scores = torch.zeros(4)

    rewards = torch.tensor([0.8, 0.6])
    uids = [1, 2]
    v.update_scores(rewards, uids)

    # After update: scores[uid] = alpha * reward + (1-alpha) * 0
    expected_1 = MOVING_AVERAGE_ALPHA * 0.8
    expected_2 = MOVING_AVERAGE_ALPHA * 0.6
    assert float(v.scores[1]) == pytest.approx(expected_1, abs=1e-5)
    assert float(v.scores[2]) == pytest.approx(expected_2, abs=1e-5)
    # UID 3 untouched
    assert float(v.scores[3]) == pytest.approx(0.0)


def test_update_scores_nan_handling(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """NaN rewards are replaced with 0 before the moving average."""
    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    v.scores = torch.zeros(4)

    rewards = torch.tensor([float("nan"), 0.5])
    v.update_scores(rewards, [1, 2])

    assert not torch.isnan(v.scores).any()
    assert float(v.scores[1]) == pytest.approx(0.0)


def test_set_weights_calls_subtensor(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """set_weights records a call on the mock subtensor."""
    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    v.scores = torch.tensor([0.0, 0.5, 0.3, 0.2])
    v.set_weights()

    assert len(mock_subtensor.set_weights_calls) == 1
    call = mock_subtensor.set_weights_calls[0]
    assert call["netuid"] is not None


def test_set_weights_normalizes(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """Weights passed to subtensor are L1-normalized (sum to 1)."""
    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    v.scores = torch.tensor([0.0, 0.6, 0.3, 0.1])
    v.set_weights()

    call = mock_subtensor.set_weights_calls[0]
    weights = call["weights"]
    weight_sum = float(weights.sum())
    assert weight_sum == pytest.approx(1.0, abs=1e-5)


async def test_run_epoch_calls_dendrite(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """run_epoch sends KnowledgeQuery and NarrativeHop synapses via the dendrite."""
    _register_handlers(mock_dendrite)
    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    await v.run_epoch()

    synapse_types = [c["synapse_type"] for c in mock_dendrite.call_log]
    assert "KnowledgeQuery" in synapse_types
    assert "NarrativeHop" in synapse_types


async def test_run_epoch_scores_nonzero(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """After a full epoch, at least one miner has a non-zero score."""
    _register_handlers(mock_dendrite)
    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    await v.run_epoch()

    miner_scores = v.scores[1:]  # UIDs 1-3 are miners
    assert miner_scores.sum() > 0


async def test_run_epoch_decays_edges(
    mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store
):
    """run_epoch calls decay_edges on the graph store."""
    _register_handlers(mock_dendrite)

    # Add an edge so we can observe decay
    graph_store.add_node("node-1")
    graph_store.add_node("node-2")
    graph_store.upsert_edge("node-1", "node-2", weight=1.0)

    edge_before = graph_store.outgoing_edge_weight_sum("node-1")

    v = _make_validator(mock_wallet, mock_subtensor, mock_dendrite, mock_metagraph, graph_store)
    await v.run_epoch()

    edge_after = graph_store.outgoing_edge_weight_sum("node-1")
    assert edge_after < edge_before

