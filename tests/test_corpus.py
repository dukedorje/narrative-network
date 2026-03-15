"""Unit tests for domain.corpus — chunking and Merkle proofs only.

.load() is NOT called — it requires SentenceTransformer.
All tests operate on _chunk_text() and MerkleProver directly.
"""

from __future__ import annotations

import hashlib

import pytest

from domain.corpus import Chunk, CorpusLoader, MerkleProver, compute_corpus_root_hash, merkle_root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chunk(text: str, index: int = 0, source_id: str = "test") -> Chunk:
    chunk_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return Chunk(
        id=f"{source_id}:{index}",
        source_id=source_id,
        text=text,
        hash=chunk_hash,
    )


def _word_text(n: int) -> str:
    """Generate a text string with exactly n whitespace-delimited words."""
    return " ".join(f"word{i}" for i in range(n))


def _make_loader(chunk_words: int = 200, overlap_words: int = 40) -> CorpusLoader:
    """CorpusLoader pointed at a non-existent dir — only _chunk_text is used."""
    return CorpusLoader(
        corpus_dir="/tmp/nonexistent",
        chunk_words=chunk_words,
        overlap_words=overlap_words,
        cache_path=None,
    )


# ---------------------------------------------------------------------------
# _chunk_text tests
# ---------------------------------------------------------------------------


def test_chunk_text_basic():
    loader = _make_loader(chunk_words=200, overlap_words=40)
    text = _word_text(500)
    chunks = loader._chunk_text(text, source_id="doc")
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.source_id == "doc"
        assert chunk.text


def test_chunk_text_overlap():
    """Consecutive chunks share overlap_words worth of words at boundaries."""
    loader = _make_loader(chunk_words=10, overlap_words=3)
    text = _word_text(30)
    chunks = loader._chunk_text(text, source_id="doc")
    assert len(chunks) >= 2
    # Last words of chunk[0] should appear at start of chunk[1]
    words0 = chunks[0].text.split()
    words1 = chunks[1].text.split()
    # The overlap means words1 starts with the last `overlap_words` of words0
    overlap = 3
    assert words0[-overlap:] == words1[:overlap]


def test_chunk_text_empty():
    loader = _make_loader()
    chunks = loader._chunk_text("", source_id="empty")
    assert chunks == []


def test_chunk_text_whitespace_only():
    loader = _make_loader()
    chunks = loader._chunk_text("   \n\t  ", source_id="ws")
    assert chunks == []


def test_chunk_hash_deterministic():
    """Same text always produces the same hash regardless of loader instance."""
    text = _word_text(50)
    loader1 = _make_loader()
    loader2 = _make_loader()
    chunks1 = loader1._chunk_text(text, source_id="src")
    chunks2 = loader2._chunk_text(text, source_id="src")
    assert len(chunks1) == len(chunks2)
    for c1, c2 in zip(chunks1, chunks2):
        assert c1.hash == c2.hash


def test_corpus_loader_chunk_text_only():
    """_chunk_text is pure text processing — no embedding, no file I/O."""
    loader = _make_loader(chunk_words=5, overlap_words=1)
    text = "alpha beta gamma delta epsilon zeta eta theta"
    chunks = loader._chunk_text(text, source_id="inline")
    assert len(chunks) >= 1
    # All chunk ids should reference the source_id
    for i, chunk in enumerate(chunks):
        assert chunk.id == f"inline:{i}"


# ---------------------------------------------------------------------------
# merkle_root helper
# ---------------------------------------------------------------------------


def test_merkle_root_empty():
    root = merkle_root([])
    assert root == b"\x00" * 32


def test_merkle_root_single():
    leaf = b"hello"
    root = merkle_root([leaf])
    assert isinstance(root, bytes)
    assert len(root) == 32


# ---------------------------------------------------------------------------
# MerkleProver tests
# ---------------------------------------------------------------------------


def test_merkle_prover_root_deterministic():
    chunks = [_make_chunk(f"chunk text {i}", i) for i in range(5)]
    root1 = MerkleProver(chunks).root
    root2 = MerkleProver(chunks).root
    assert root1 == root2
    assert len(root1) == 64  # hex string


def test_merkle_prove_verify_roundtrip():
    chunks = [_make_chunk(f"text {i}", i) for i in range(4)]
    prover = MerkleProver(chunks)
    for i in range(len(chunks)):
        proof = prover.prove(i)
        assert MerkleProver.verify(proof, prover.root) is True


def test_merkle_verify_wrong_root():
    chunks = [_make_chunk(f"text {i}", i) for i in range(4)]
    prover = MerkleProver(chunks)
    proof = prover.prove(0)
    wrong_root = "a" * 64
    assert MerkleProver.verify(proof, wrong_root) is False


def test_merkle_verify_tampered_proof():
    chunks = [_make_chunk(f"text {i}", i) for i in range(4)]
    prover = MerkleProver(chunks)
    proof = prover.prove(0)
    # Tamper the leaf hash
    tampered = dict(proof)
    tampered["leaf_hash"] = "ff" * 32
    assert MerkleProver.verify(tampered, prover.root) is False


def test_merkle_prover_multiple_chunks():
    chunks = [_make_chunk(f"paragraph {i} with some extra words", i) for i in range(15)]
    prover = MerkleProver(chunks)
    # Prove and verify all 15 chunks
    for i in range(15):
        proof = prover.prove(i)
        assert MerkleProver.verify(proof, prover.root) is True


def test_compute_corpus_root_hash():
    chunks = [_make_chunk(f"text {i}", i) for i in range(6)]
    prover = MerkleProver(chunks)
    computed = compute_corpus_root_hash(chunks)
    assert computed == prover.root


def test_merkle_empty_corpus():
    """MerkleProver with empty chunk list returns zero root (64 hex zeros)."""
    prover = MerkleProver([])
    assert prover.root == "0" * 64


# ---------------------------------------------------------------------------
# Edge-case tree sizes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("n_chunks", [1, 2, 3, 7, 8, 15, 16])
def test_merkle_prover_tree_sizes(n_chunks):
    """Prove/verify roundtrip for various tree sizes covering odd/even padding."""
    chunks = []
    for i in range(n_chunks):
        text = f"Chunk {i} content for tree size test {n_chunks}"
        chunks.append(Chunk(
            id=f"size-test:{i}",
            source_id="size-test",
            text=text,
            hash=hashlib.sha256(text.encode()).hexdigest(),
        ))

    prover = MerkleProver(chunks)
    assert prover.root  # non-empty root
    assert len(prover.root) == 64  # valid hex sha256

    # Verify every chunk proves correctly
    for i in range(n_chunks):
        proof = prover.prove(i)
        assert MerkleProver.verify(proof, prover.root), f"Chunk {i} failed for tree size {n_chunks}"


def test_chunk_text_single_word():
    """Single word text produces one chunk."""
    loader = CorpusLoader(corpus_dir="/tmp/nonexistent", chunk_words=200)
    chunks = loader._chunk_text("hello", source_id="single")
    assert len(chunks) == 1
    assert chunks[0].text == "hello"


def test_chunk_text_exactly_max_words():
    """Text exactly at chunk_words (with no overlap) produces one chunk."""
    loader = CorpusLoader(corpus_dir="/tmp/nonexistent", chunk_words=10, overlap_words=0)
    text = " ".join(["word"] * 10)
    chunks = loader._chunk_text(text, source_id="exact")
    assert len(chunks) == 1
    assert len(chunks[0].text.split()) == 10
