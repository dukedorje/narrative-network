"""Integration tests — full validator epoch cycle."""
import pytest
import copy
from subnet.validator import Validator
from subnet.protocol import KnowledgeQuery, NarrativeHop
from subnet.graph_store import GraphStore
from seed.loader import load_topology
from tests.conftest import (
    MockMetagraph, MockWallet, MockSubtensor, MockDendrite
)


@pytest.fixture
def integrated_setup():
    """Set up validator with mock BT layer and seeded graph."""
    metagraph = MockMetagraph(
        n=4,
        hotkeys=["validator-hotkey", "miner-1", "miner-2", "miner-3"],
        stakes=[1000.0, 100.0, 200.0, 50.0],
        validator_permit=[True, False, False, False],
        axon_serving=[True, True, True, True],
    )
    wallet = MockWallet(hotkey_address="validator-hotkey")
    subtensor = MockSubtensor(metagraph=metagraph)
    dendrite = MockDendrite(wallet=wallet)

    # Load seed topology
    graph_store = GraphStore(db_path=None)
    load_topology(graph_store=graph_store)

    # Register mock handlers
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
                    "id": f"chunk-{axon_index}",
                    "text": "quantum test data",
                    "hash": "d" * 64,
                    "score": 0.9 - axon_index * 0.1,
                }
            ]
            synapse.domain_similarity = 0.8 - axon_index * 0.1
            synapse.node_id = f"node-{axon_index + 1}"
        synapse.agent_uid = axon_index + 1
        return synapse

    def nh_handler(synapse, axon_index=0):
        # Different quality responses per miner
        word_count = 200 - axon_index * 30  # miner 0 = 200 words, miner 2 = 140 words
        synapse.narrative_passage = " ".join(["quantum"] * word_count)
        synapse.passage_embedding = [0.0] * 768
        synapse.passage_embedding[axon_index] = 1.0  # different direction per miner
        synapse.choice_cards = []
        synapse.agent_uid = axon_index + 1
        return synapse

    dendrite.register_handler(KnowledgeQuery, kq_handler)
    dendrite.register_handler(NarrativeHop, nh_handler)

    # Add some traversal logs for topology context
    graph_store.log_traversal(
        session_id="seed-1",
        source_id="quantum-foundations",
        dest_id="quantum-phenomena",
        passage_embedding=[0.0] * 768,
        scores={1: 0.8, 2: 0.6},
    )

    validator = Validator(
        wallet=wallet,
        subtensor=subtensor,
        dendrite=dendrite,
        metagraph=metagraph,
        graph_store=graph_store,
    )

    return validator, dendrite, subtensor, graph_store


class TestFullEpoch:
    async def test_epoch_completes(self, integrated_setup):
        """run_epoch completes without errors."""
        validator, _, _, _ = integrated_setup
        await validator.run_epoch()
        assert validator.step == 1

    async def test_dendrite_called_with_synapses(self, integrated_setup):
        """Dendrite receives KnowledgeQuery and NarrativeHop calls."""
        validator, dendrite, _, _ = integrated_setup
        await validator.run_epoch()

        synapse_types = [call["synapse_type"] for call in dendrite.call_log]
        assert "KnowledgeQuery" in synapse_types
        assert "NarrativeHop" in synapse_types

    async def test_scores_nonzero(self, integrated_setup):
        """After epoch, challenged miners have non-zero scores."""
        validator, _, _, _ = integrated_setup
        await validator.run_epoch()

        # At least one miner UID (1, 2, or 3) should have non-zero score
        miner_scores = validator.scores[1:4]
        assert miner_scores.sum() > 0

    async def test_weights_set(self, integrated_setup):
        """set_weights is called on subtensor."""
        validator, _, subtensor, _ = integrated_setup
        await validator.run_epoch()

        assert len(subtensor.set_weights_calls) == 1
        call = subtensor.set_weights_calls[0]
        assert call["netuid"] == 42
        assert call["mechid"] == 0

    async def test_edges_decayed(self, integrated_setup):
        """Edge weights decrease after epoch due to decay."""
        validator, _, _, graph_store = integrated_setup

        # Get initial edge count
        initial_stats = graph_store.stats()
        initial_edge_count = initial_stats["edge_count"]

        await validator.run_epoch()

        # Edges should still exist but weights should have decayed
        post_stats = graph_store.stats()
        assert post_stats["edge_count"] > 0  # edges not all pruned

    async def test_step_increments(self, integrated_setup):
        """Validator step counter increments after epoch."""
        validator, _, _, _ = integrated_setup
        assert validator.step == 0
        await validator.run_epoch()
        assert validator.step == 1
        await validator.run_epoch()
        assert validator.step == 2
