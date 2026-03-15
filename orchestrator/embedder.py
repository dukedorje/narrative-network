"""Sentence-transformer wrapper for embedding queries and passages."""

from __future__ import annotations

import numpy as np


class Embedder:
    """Thin wrapper around a SentenceTransformer model.

    Lazy-loads the model on first use to avoid import-time CUDA initialisation.
    """

    def __init__(self, model_name: str = "all-mpnet-base-v2", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.model_name, device=self.device)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns a list of flat float vectors."""
        self._load()
        vectors = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return vectors.tolist()

    def embed_one(self, text: str) -> list[float]:
        """Embed a single text. Returns a flat float vector."""
        return self.embed([text])[0]
