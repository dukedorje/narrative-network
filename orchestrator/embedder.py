"""ONNX Runtime sentence embedder — drop-in replacement for SentenceTransformer.

Eliminates ~700 MB of dependencies (torch, scipy, sklearn, sympy) by using
ONNX Runtime for inference with the HuggingFace tokenizers library.
"""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)


class Embedder:
    """Sentence embedder using ONNX Runtime instead of PyTorch.

    Same API as the previous SentenceTransformer-based embedder.
    Lazy-loads model on first use to avoid import-time overhead.
    """

    def __init__(self, model_name: str = "all-mpnet-base-v2", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._session = None
        self._tokenizer = None
        self._input_names: set[str] = set()

    def _load(self) -> None:
        if self._session is not None:
            return

        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        repo_id = self.model_name
        if "/" not in repo_id:
            repo_id = f"sentence-transformers/{repo_id}"

        onnx_path = hf_hub_download(repo_id, "onnx/model.onnx")
        tokenizer_path = hf_hub_download(repo_id, "tokenizer.json")

        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._tokenizer.enable_padding()
        self._tokenizer.enable_truncation(max_length=512)

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 2

        self._session = ort.InferenceSession(
            onnx_path, sess_options, providers=["CPUExecutionProvider"]
        )
        self._input_names = {inp.name for inp in self._session.get_inputs()}

        log.info("Loaded ONNX embedder: %s", repo_id)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns a list of flat float vectors."""
        self._load()

        encodings = self._tokenizer.encode_batch(texts)

        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)

        feeds: dict[str, np.ndarray] = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        outputs = self._session.run(None, feeds)

        token_embeddings = outputs[0]

        if len(token_embeddings.shape) == 2:
            # Already pooled (batch, hidden_dim)
            mean_pooled = token_embeddings
        else:
            # Token-level (batch, seq_len, hidden_dim) — mean pool with attention mask
            mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
            summed = (token_embeddings * mask_expanded).sum(axis=1)
            counts = mask_expanded.sum(axis=1).clip(min=1e-9)
            mean_pooled = summed / counts

        # L2 normalize
        norms = np.linalg.norm(mean_pooled, axis=1, keepdims=True).clip(min=1e-9)
        normalized = mean_pooled / norms

        return normalized.tolist()

    def embed_one(self, text: str) -> list[float]:
        """Embed a single text. Returns a flat float vector."""
        return self.embed([text])[0]
