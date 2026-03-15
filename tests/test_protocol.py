"""Tests for synapse protocol definitions."""

from subnet.protocol import ChoiceCard, KnowledgeQuery, NarrativeHop, WeightCommit


def test_knowledge_query_defaults():
    kq = KnowledgeQuery()
    assert kq.top_k == 5
    assert kq.chunks is None
    assert kq.spec_version == "1"


def test_narrative_hop_defaults():
    nh = NarrativeHop()
    assert nh.destination_node_id == ""
    assert nh.narrative_passage is None
    assert nh.choice_cards is None
    assert nh.integration_notice is None


def test_weight_commit_normalise():
    wc = WeightCommit(epoch=1, validator_uid=0, miner_scores={0: 3.0, 1: 1.0, 2: 1.0})
    wc.normalise()
    assert abs(sum(wc.miner_scores.values()) - 1.0) < 1e-9
    assert abs(wc.miner_scores[0] - 0.6) < 1e-9


def test_weight_commit_to_arrays():
    wc = WeightCommit(epoch=1, validator_uid=0, miner_scores={5: 0.5, 10: 0.3, 15: 0.2})
    uids, weights = wc.to_arrays()
    assert uids == [5, 10, 15]
    assert weights == [0.5, 0.3, 0.2]


def test_choice_card_model():
    card = ChoiceCard(text="Enter the void", destination_node_id="void-01")
    assert card.edge_weight_delta == 0.0
    assert card.thematic_color == "#888888"
