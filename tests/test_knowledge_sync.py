"""Tests for domain.knowledge_sync — KnowledgeSyncGate relevance checking."""

from __future__ import annotations

from domain.knowledge_sync import (
    KnowledgeSyncGate,
    KnowledgeSyncRequest,
    KnowledgeSyncResponse,
)


class TestKnowledgeSyncGate:
    def test_identical_centroids_accepted(self):
        """Identical centroids have zero distance — should be accepted."""
        gate = KnowledgeSyncGate(max_cosine_distance=0.35)
        centroid = [1.0, 0.0, 0.0]
        assert gate.check_relevance(centroid, centroid) is True

    def test_similar_centroids_accepted(self):
        """Close centroids within threshold should be accepted."""
        gate = KnowledgeSyncGate(max_cosine_distance=0.35)
        src = [1.0, 0.0, 0.0]
        tgt = [0.9, 0.1, 0.0]  # close to src
        assert gate.check_relevance(src, tgt) is True

    def test_distant_centroids_rejected(self):
        """Orthogonal centroids (distance=1.0) should be rejected."""
        gate = KnowledgeSyncGate(max_cosine_distance=0.35)
        src = [1.0, 0.0, 0.0]
        tgt = [0.0, 1.0, 0.0]  # orthogonal
        assert gate.check_relevance(src, tgt) is False

    def test_opposite_centroids_rejected(self):
        """Opposite centroids (distance=2.0) should be rejected."""
        gate = KnowledgeSyncGate(max_cosine_distance=0.35)
        src = [1.0, 0.0, 0.0]
        tgt = [-1.0, 0.0, 0.0]
        assert gate.check_relevance(src, tgt) is False

    def test_zero_vector_rejected(self):
        """Zero vector centroids should be rejected."""
        gate = KnowledgeSyncGate(max_cosine_distance=0.35)
        assert gate.check_relevance([0.0, 0.0], [1.0, 0.0]) is False
        assert gate.check_relevance([1.0, 0.0], [0.0, 0.0]) is False

    def test_custom_threshold(self):
        """Custom threshold should be respected."""
        strict_gate = KnowledgeSyncGate(max_cosine_distance=0.01)
        loose_gate = KnowledgeSyncGate(max_cosine_distance=0.99)
        src = [1.0, 0.0]
        tgt = [0.9, 0.4]  # moderate distance
        assert strict_gate.check_relevance(src, tgt) is False
        assert loose_gate.check_relevance(src, tgt) is True

    def test_filter_chunks_keeps_relevant(self):
        """filter_chunks keeps chunks close to target centroid."""
        gate = KnowledgeSyncGate(max_cosine_distance=0.35)
        target = [1.0, 0.0, 0.0]
        chunks = ["relevant chunk", "irrelevant chunk"]
        embeddings = [
            [0.95, 0.05, 0.0],  # close to target
            [0.0, 0.0, 1.0],  # far from target
        ]
        result = gate.filter_chunks(chunks, target, embeddings)
        assert "relevant chunk" in result
        assert "irrelevant chunk" not in result

    def test_filter_chunks_empty_input(self):
        """filter_chunks returns empty for empty input."""
        gate = KnowledgeSyncGate()
        assert gate.filter_chunks([], [1.0, 0.0], []) == []
        assert gate.filter_chunks(["chunk"], [], []) == []

    def test_filter_chunks_zero_embedding_skipped(self):
        """Chunks with zero embeddings are skipped."""
        gate = KnowledgeSyncGate(max_cosine_distance=0.99)
        result = gate.filter_chunks(
            ["chunk"],
            [1.0, 0.0],
            [[0.0, 0.0]],
        )
        assert result == []


class TestKnowledgeSyncDataclasses:
    def test_request_creation(self):
        req = KnowledgeSyncRequest(
            source_node_id="node-a",
            target_node_id="node-b",
            chunks=["hello world"],
            centroid_embedding=[0.1, 0.2],
        )
        assert req.source_node_id == "node-a"
        assert len(req.chunks) == 1

    def test_response_defaults(self):
        resp = KnowledgeSyncResponse()
        assert resp.accepted_chunks == []
        assert resp.rejected_reason is None

    def test_response_with_rejection(self):
        resp = KnowledgeSyncResponse(
            rejected_reason="centroids too distant"
        )
        assert resp.rejected_reason == "centroids too distant"
