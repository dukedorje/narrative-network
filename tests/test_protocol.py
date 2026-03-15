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


def test_weight_commit_normalise_sums_to_one():
    """After normalise(), weights sum to 1.0."""
    wc = WeightCommit(epoch=1, validator_uid=0, miner_scores={0: 5.0, 1: 3.0, 2: 2.0})
    wc.normalise()
    assert abs(sum(wc.miner_scores.values()) - 1.0) < 1e-9


def test_weight_commit_normalise_preserves_zero():
    """Zero-score miners remain at 0 after normalisation (they get 0/total = 0)."""
    wc = WeightCommit(epoch=1, validator_uid=0, miner_scores={0: 4.0, 1: 0.0, 2: 6.0})
    wc.normalise()
    assert wc.miner_scores[1] == 0.0
    assert abs(sum(wc.miner_scores.values()) - 1.0) < 1e-9


def test_weight_commit_normalise_all_zero():
    """All-zero scores remain all-zero (0/0 = 0, no division by zero)."""
    wc = WeightCommit(epoch=1, validator_uid=0, miner_scores={0: 0.0, 1: 0.0})
    wc.normalise()
    assert wc.miner_scores[0] == 0.0
    assert wc.miner_scores[1] == 0.0
