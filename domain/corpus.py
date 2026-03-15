"""Corpus loader, chunker, embedder, and Merkle prover.

NO ChromaDB dependency — all in-memory/numpy with optional disk cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from subnet.config import EMBEDDING_MODEL, EMBEDDING_DIM

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _word_positions(text: str) -> list[tuple[int, int]]:
    """Return (start, end) byte offsets for each whitespace-delimited word."""
    positions: list[tuple[int, int]] = []
    start = None
    for i, ch in enumerate(text):
        if ch.isspace():
            if start is not None:
                positions.append((start, i))
                start = None
        else:
            if start is None:
                start = i
    if start is not None:
        positions.append((start, len(text)))
    return positions


def merkle_root(leaves: list[bytes]) -> bytes:
    """Compute SHA-256 binary Merkle root from leaf byte strings."""
    if not leaves:
        return b"\x00" * 32
    layer = [_sha256(leaf) for leaf in leaves]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [_sha256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


def compute_corpus_root_hash(chunks: list[Chunk]) -> str:
    """Return hex Merkle root over all chunk hashes in order."""
    leaves = [bytes.fromhex(c.hash) for c in chunks]
    return merkle_root(leaves).hex()


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    id: str                      # "<source_id>:<index>"
    source_id: str               # filename stem
    text: str
    hash: str                    # sha256 hex of text.encode()
    embedding: list[float] = field(default_factory=list)
    char_start: int = 0
    char_end: int = 0


# ---------------------------------------------------------------------------
# CorpusLoader
# ---------------------------------------------------------------------------

class CorpusLoader:
    """Load .txt/.md from a directory, chunk with overlap, embed, cache to disk.

    Parameters
    ----------
    corpus_dir:
        Directory containing source documents (.txt / .md).
    chunk_words:
        Target chunk size in words.
    overlap_words:
        Overlap between consecutive chunks in words.
    model_name:
        SentenceTransformer model name for embedding.
    cache_path:
        If given, chunks + embeddings are pickled here and reloaded on next run.
    """

    def __init__(
        self,
        corpus_dir: str | Path,
        chunk_words: int = 200,
        overlap_words: int = 40,
        model_name: str = EMBEDDING_MODEL,
        cache_path: str | Path | None = None,
    ) -> None:
        self.corpus_dir = Path(corpus_dir)
        self.chunk_words = chunk_words
        self.overlap_words = overlap_words
        self.model_name = model_name
        self.cache_path = Path(cache_path) if cache_path else None

        self.chunks: list[Chunk] = []
        self.centroid: list[float] = [0.0] * EMBEDDING_DIM
        self._embedder = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> list[Chunk]:
        """Load (or restore from cache) all chunks with embeddings."""
        if self.cache_path and self.cache_path.exists():
            log.info("Restoring corpus from cache %s", self.cache_path)
            self.chunks = self._load_cache()
        else:
            self.chunks = self._load_from_disk()
            self._embed_chunks()
            if self.cache_path:
                self._save_cache()
        self.centroid = self._compute_centroid()
        return self.chunks

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_from_disk(self) -> list[Chunk]:
        chunks: list[Chunk] = []
        for path in sorted(self.corpus_dir.iterdir()):
            if path.suffix not in {".txt", ".md"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            file_chunks = self._chunk_text(text, source_id=path.stem)
            chunks.extend(file_chunks)
            log.debug("Loaded %d chunks from %s", len(file_chunks), path.name)
        log.info("Total chunks loaded from disk: %d", len(chunks))
        return chunks

    def _chunk_text(self, text: str, source_id: str) -> list[Chunk]:
        positions = _word_positions(text)
        if not positions:
            return []

        chunks: list[Chunk] = []
        step = max(1, self.chunk_words - self.overlap_words)
        idx = 0
        chunk_index = 0

        while idx < len(positions):
            end_idx = min(idx + self.chunk_words, len(positions))
            char_start = positions[idx][0]
            char_end = positions[end_idx - 1][1]
            chunk_text = text[char_start:char_end]
            chunk_hash = _sha256_hex(chunk_text.encode("utf-8"))
            chunks.append(
                Chunk(
                    id=f"{source_id}:{chunk_index}",
                    source_id=source_id,
                    text=chunk_text,
                    hash=chunk_hash,
                    char_start=char_start,
                    char_end=char_end,
                )
            )
            chunk_index += 1
            idx += step

        return chunks

    def _get_embedder(self):
        if self._embedder is None:
            from orchestrator.embedder import Embedder
            self._embedder = Embedder(model_name=self.model_name)
        return self._embedder

    def _embed_chunks(self) -> None:
        if not self.chunks:
            return
        embedder = self._get_embedder()
        batch_size = 32
        texts = [c.text for c in self.chunks]
        all_embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            all_embeddings.extend(embedder.embed(batch))
        for chunk, emb in zip(self.chunks, all_embeddings):
            chunk.embedding = emb

    def _compute_centroid(self) -> list[float]:
        if not self.chunks or not self.chunks[0].embedding:
            return [0.0] * EMBEDDING_DIM
        mat = np.array([c.embedding for c in self.chunks], dtype=np.float32)
        centroid = mat.mean(axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        return centroid.tolist()

    def _save_cache(self) -> None:
        assert self.cache_path is not None
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "wb") as f:
            pickle.dump(self.chunks, f)
        log.info("Corpus cached to %s", self.cache_path)

    def _load_cache(self) -> list[Chunk]:
        assert self.cache_path is not None
        with open(self.cache_path, "rb") as f:
            return pickle.load(f)


# ---------------------------------------------------------------------------
# MerkleProver
# ---------------------------------------------------------------------------

class MerkleProver:
    """SHA-256 binary Merkle tree with inclusion proof generation and verification.

    Parameters
    ----------
    chunks:
        Ordered list of Chunk objects. Order must be stable across prove/verify.
    """

    def __init__(self, chunks: list[Chunk]) -> None:
        self._leaves: list[bytes] = [bytes.fromhex(c.hash) for c in chunks]
        self._tree: list[list[bytes]] = self._build_tree()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def root(self) -> str:
        """Hex-encoded Merkle root."""
        if not self._tree:
            return "0" * 64
        return self._tree[-1][0].hex()

    def prove(self, chunk_index: int) -> dict:
        """Return a JSON-serialisable inclusion proof for chunk at *chunk_index*.

        Proof format::

            {
                "leaf_index": int,
                "leaf_hash": str,       # hex
                "siblings": [           # bottom-up sibling hashes
                    {"hash": str, "position": "left" | "right"}
                ],
                "root": str             # hex Merkle root
            }
        """
        if not self._leaves:
            raise ValueError("Empty corpus — no proof possible")
        if chunk_index < 0 or chunk_index >= len(self._leaves):
            raise IndexError(f"chunk_index {chunk_index} out of range [0, {len(self._leaves)})")

        siblings: list[dict] = []
        idx = chunk_index

        for layer in self._tree[:-1]:  # skip root layer
            if idx % 2 == 0:
                sibling_idx = idx + 1 if idx + 1 < len(layer) else idx
                position = "right"
            else:
                sibling_idx = idx - 1
                position = "left"
            siblings.append({"hash": layer[sibling_idx].hex(), "position": position})
            idx //= 2

        return {
            "leaf_index": chunk_index,
            "leaf_hash": self._leaves[chunk_index].hex(),
            "siblings": siblings,
            "root": self.root,
        }

    @staticmethod
    def verify(proof: dict, expected_root: str) -> bool:
        """Validate an inclusion proof against *expected_root*.

        Returns True iff the proof is mathematically valid.
        """
        try:
            current = bytes.fromhex(proof["leaf_hash"])
            for sibling in proof["siblings"]:
                sib = bytes.fromhex(sibling["hash"])
                if sibling["position"] == "left":
                    current = _sha256(sib + current)
                else:
                    current = _sha256(current + sib)
            return current.hex() == expected_root
        except (KeyError, ValueError):
            return False

    # ------------------------------------------------------------------
    # Tree construction
    # ------------------------------------------------------------------

    def _build_tree(self) -> list[list[bytes]]:
        if not self._leaves:
            return []
        layer = [_sha256(leaf) for leaf in self._leaves]
        tree = [layer]
        while len(layer) > 1:
            if len(layer) % 2 == 1:
                layer = layer + [layer[-1]]
            layer = [_sha256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
            tree.append(layer)
        return tree
