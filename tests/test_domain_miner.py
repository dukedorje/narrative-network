"""Unit tests for domain.miner.DomainMiner._forward() without real BT dependencies."""

import hashlib

import numpy as np
import pytest

from domain.corpus import Chunk, MerkleProver
from domain.miner import DomainMiner
from subnet.protocol import KnowledgeQuery


# ---------------------------------------------------------------------------
# Minimal stand-in — only the attributes _forward needs
# ---------------------------------------------------------------------------


class MinimalDomainMiner:
    """Minimal stand-in with just the attributes _forward needs."""

    def __init__(self, chunks, merkle_prover, node_id="test-node", uid=1):
        self.chunks = chunks
        self.merkle_prover = merkle_prover
        self.corpus_root_hash = merkle_prover.root if merkle_prover else ""
        self.centroid = [1.0] + [0.0] * 767
        self.node_id = node_id
        self.uid = uid


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def domain_miner_components():
    """Create corpus components without real BT dependencies."""
    chunks = []
    for i in range(5):
        text = f"Test chunk {i} about quantum mechanics topic number {i}"
        embedding = [0.0] * 768
        embedding[i] = 1.0  # orthogonal unit vectors
        chunks.append(
            Chunk(
                id=f"test:{i}",
                source_id="test",
                text=text,
                hash=hashlib.sha256(text.encode()).hexdigest(),
                embedding=embedding,
                char_start=0,
                char_end=len(text),
            )
        )

    prover = MerkleProver(chunks)
    return chunks, prover


@pytest.fixture
def minimal_miner(domain_miner_components):
    chunks, prover = domain_miner_components
    return MinimalDomainMiner(chunks=chunks, merkle_prover=prover)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_forward_chunk_retrieval(minimal_miner):
    """Sending a query with an embedding returns ranked chunks."""
    # Query embedding aligned with chunk 0 (index 0 == 1.0)
    query_embedding = [0.0] * 768
    query_embedding[0] = 1.0

    synapse = KnowledgeQuery(
        query_text="quantum mechanics",
        query_embedding=query_embedding,
        top_k=3,
    )

    result = await DomainMiner._forward(minimal_miner, synapse)

    assert result.chunks is not None
    assert len(result.chunks) > 0
    # Chunk 0 should score highest (dot product == 1.0)
    assert result.chunks[0]["id"] == "test:0"
    assert result.domain_similarity is not None


async def test_forward_corpus_challenge(minimal_miner):
    """Corpus challenge returns a valid Merkle proof."""
    synapse = KnowledgeQuery(query_text="__corpus_challenge__")

    result = await DomainMiner._forward(minimal_miner, synapse)

    assert result.merkle_proof is not None
    assert "leaf_hash" in result.merkle_proof
    assert "siblings" in result.merkle_proof
    assert "root" in result.merkle_proof
    assert result.node_id == "test-node"
    assert result.agent_uid == 1


async def test_forward_empty_corpus():
    """No chunks loaded — returns empty chunk list."""
    miner = MinimalDomainMiner(chunks=[], merkle_prover=None, node_id="empty-node", uid=2)
    miner.merkle_prover = None

    query_embedding = [0.0] * 768
    query_embedding[0] = 1.0

    synapse = KnowledgeQuery(
        query_text="anything",
        query_embedding=query_embedding,
        top_k=5,
    )

    result = await DomainMiner._forward(miner, synapse)

    assert result.chunks == []
    assert result.domain_similarity == 0.0
    assert result.node_id == "empty-node"
    assert result.agent_uid == 2


async def test_forward_empty_query_embedding(minimal_miner):
    """Empty query embedding returns empty chunks."""
    synapse = KnowledgeQuery(
        query_text="quantum",
        query_embedding=[],  # empty
        top_k=5,
    )

    result = await DomainMiner._forward(minimal_miner, synapse)

    assert result.chunks == []
    assert result.domain_similarity == 0.0


async def test_forward_sets_node_id_and_uid(minimal_miner):
    """Response carries the correct node_id and agent_uid."""
    query_embedding = [0.0] * 768
    query_embedding[2] = 1.0

    synapse = KnowledgeQuery(
        query_text="test",
        query_embedding=query_embedding,
        top_k=2,
    )

    result = await DomainMiner._forward(minimal_miner, synapse)

    assert result.node_id == "test-node"
    assert result.agent_uid == 1
