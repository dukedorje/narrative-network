"""Tests for corpus integrity challenge flow."""
import pytest
import hashlib
from domain.corpus import Chunk, MerkleProver
from subnet.reward import score_corpus


@pytest.fixture
def corpus_with_prover():
    """Create a small corpus with a MerkleProver."""
    chunks = []
    for i in range(5):
        text = f"Quantum mechanics chunk number {i} with unique content about topic {i}"
        chunks.append(Chunk(
            id=f"test:{i}",
            source_id="test",
            text=text,
            hash=hashlib.sha256(text.encode()).hexdigest(),
        ))
    prover = MerkleProver(chunks)
    return chunks, prover


class TestCorpusChallenge:
    def test_prove_and_verify(self, corpus_with_prover):
        """Valid proof verifies against correct root."""
        chunks, prover = corpus_with_prover
        for i in range(len(chunks)):
            proof = prover.prove(i)
            assert MerkleProver.verify(proof, prover.root)

    def test_wrong_root_fails(self, corpus_with_prover):
        """Proof does not verify against a different root."""
        _, prover = corpus_with_prover
        proof = prover.prove(0)
        wrong_root = "f" * 64
        assert not MerkleProver.verify(proof, wrong_root)

    def test_tampered_leaf_fails(self, corpus_with_prover):
        """Modifying the leaf hash invalidates the proof."""
        _, prover = corpus_with_prover
        proof = prover.prove(0)
        proof["leaf_hash"] = "0" * 64  # tamper
        assert not MerkleProver.verify(proof, prover.root)

    def test_tampered_sibling_fails(self, corpus_with_prover):
        """Modifying a sibling hash invalidates the proof."""
        _, prover = corpus_with_prover
        proof = prover.prove(0)
        if proof["siblings"]:
            proof["siblings"][0]["hash"] = "0" * 64
        assert not MerkleProver.verify(proof, prover.root)

    def test_score_corpus_valid(self):
        """Valid merkle root match scores 1.0."""
        assert score_corpus(merkle_root_matches=True) == 1.0

    def test_score_corpus_fraud(self):
        """Failed merkle match scores 0.0."""
        assert score_corpus(merkle_root_matches=False) == 0.0

    def test_score_corpus_partial(self):
        """Partial match scores 0.3."""
        assert score_corpus(merkle_root_matches=False, partial_match=True) == 0.3

    def test_end_to_end_challenge_flow(self, corpus_with_prover):
        """Full flow: generate proof, verify, score."""
        chunks, prover = corpus_with_prover

        # Validator sends challenge, miner responds with proof
        proof = prover.prove(2)

        # Validator verifies
        is_valid = MerkleProver.verify(proof, prover.root)

        # Validator scores
        score = score_corpus(merkle_root_matches=is_valid)
        assert score == 1.0

    def test_end_to_end_fraud_detection(self, corpus_with_prover):
        """Full flow: detect fraud when miner tampers with corpus."""
        _, prover = corpus_with_prover

        proof = prover.prove(0)
        # Simulate miner changing corpus (different root)
        tampered_root = "e" * 64

        is_valid = MerkleProver.verify(proof, tampered_root)
        score = score_corpus(merkle_root_matches=is_valid)
        assert score == 0.0
