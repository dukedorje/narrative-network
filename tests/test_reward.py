"""Tests for reward/scoring functions."""

from subnet.reward import cosine_similarity, score_corpus, score_quality, score_topology, score_traversal


def test_cosine_similarity_identical():
    v = [1.0, 0.0, 0.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert abs(cosine_similarity(a, b)) < 1e-9


def test_cosine_similarity_empty():
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0], []) == 0.0


def test_score_traversal_no_latency():
    score = score_traversal(
        chunks_embedding=[1.0, 0.0],
        query_embedding=[1.0, 0.0],
        domain_centroid=[1.0, 0.0],
        passage_embedding=[1.0, 0.0],
        process_time=1.0,
    )
    assert abs(score - 1.0) < 1e-9


def test_score_traversal_with_latency():
    score = score_traversal(
        chunks_embedding=[1.0, 0.0],
        query_embedding=[1.0, 0.0],
        domain_centroid=[1.0, 0.0],
        passage_embedding=[1.0, 0.0],
        process_time=5.0,  # 2s over soft limit
    )
    assert score < 1.0
    assert score > 0.0


def test_score_quality_good_passage():
    score = score_quality(
        passage_embedding=[1.0, 0.0],
        path_embeddings=[[1.0, 0.0]],
        destination_centroid=[1.0, 0.0],
        source_centroid=[0.0, 1.0],
        passage_text=" ".join(["word"] * 200),
    )
    assert score > 0.5


def test_score_quality_too_short():
    score = score_quality(
        passage_embedding=[1.0, 0.0],
        path_embeddings=[[1.0, 0.0]],
        destination_centroid=[1.0, 0.0],
        source_centroid=[0.0, 1.0],
        passage_text="too short",
    )
    # Length penalty should reduce score
    assert score < 0.8


def test_score_topology():
    score = score_topology(betweenness_centrality=0.5, outgoing_edge_weight_sum=10.0)
    assert 0.0 < score < 1.0


def test_score_corpus_match():
    assert score_corpus(merkle_root_matches=True) == 1.0


def test_score_corpus_fraud():
    assert score_corpus(merkle_root_matches=False) == 0.0


def test_score_corpus_partial():
    assert score_corpus(merkle_root_matches=False, partial_match=True) == 0.3
