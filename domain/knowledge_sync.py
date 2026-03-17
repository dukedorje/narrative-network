"""Knowledge sync gate for sharing chunks between nearby graph nodes.

Stub for knowledge sharing between nearby nodes. Integrates with Unbrowse
for external knowledge enrichment. Full sync protocol is future work.

Sync flow (future):
1. Miner A discovers nearby node B (centroid cosine distance < threshold)
2. A sends KnowledgeSyncRequest with its chunks to B
3. B's KnowledgeSyncGate checks relevance (centroid distance)
4. B filters and accepts only chunks within distance threshold
5. Accepted chunks are added to B's corpus

Integration points:
- Miner._forward_kq: additional chunk source from synced knowledge
- UnbrowseClient.fetch_context: external enrichment during sync
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from subnet.config import DRIFT_MAX_COSINE_DISTANCE

log = logging.getLogger(__name__)


@dataclass
class KnowledgeSyncRequest:
    """Request to share knowledge chunks between nearby nodes."""

    source_node_id: str
    target_node_id: str
    chunks: list[str]
    centroid_embedding: list[float]


@dataclass
class KnowledgeSyncResponse:
    """Response to a knowledge sync request."""

    accepted_chunks: list[str] = field(default_factory=list)
    rejected_reason: str | None = None


class KnowledgeSyncGate:
    """Gate for filtering knowledge sync requests by centroid distance.

    Checks that the source and target node centroids are within a
    configurable cosine distance threshold before accepting shared chunks.
    """

    def __init__(self, max_cosine_distance: float = DRIFT_MAX_COSINE_DISTANCE) -> None:
        self.max_cosine_distance = max_cosine_distance

    def check_relevance(
        self,
        source_centroid: list[float],
        target_centroid: list[float],
    ) -> bool:
        """Check if two centroids are within the cosine distance threshold.

        Returns True if the centroids are close enough for knowledge sharing.
        """
        src = np.array(source_centroid, dtype=np.float32)
        tgt = np.array(target_centroid, dtype=np.float32)

        src_norm = np.linalg.norm(src)
        tgt_norm = np.linalg.norm(tgt)

        if src_norm == 0 or tgt_norm == 0:
            return False

        cosine_similarity = float(np.dot(src, tgt) / (src_norm * tgt_norm))
        cosine_distance = 1.0 - cosine_similarity

        return cosine_distance <= self.max_cosine_distance

    def filter_chunks(
        self,
        chunks: list[str],
        target_centroid: list[float],
        chunk_embeddings: list[list[float]],
    ) -> list[str]:
        """Filter chunks, keeping only those close to the target centroid.

        Args:
            chunks: Text chunks to filter.
            target_centroid: Target node's centroid embedding.
            chunk_embeddings: Embeddings for each chunk (parallel to chunks list).

        Returns:
            List of chunks whose embeddings are within distance threshold of target.
        """
        if not chunks or not target_centroid:
            return []

        tgt = np.array(target_centroid, dtype=np.float32)
        tgt_norm = np.linalg.norm(tgt)
        if tgt_norm == 0:
            return []
        tgt = tgt / tgt_norm

        accepted = []
        for chunk, emb in zip(chunks, chunk_embeddings):
            emb_arr = np.array(emb, dtype=np.float32)
            emb_norm = np.linalg.norm(emb_arr)
            if emb_norm == 0:
                continue
            emb_arr = emb_arr / emb_norm
            cosine_distance = 1.0 - float(np.dot(emb_arr, tgt))
            if cosine_distance <= self.max_cosine_distance:
                accepted.append(chunk)

        return accepted
