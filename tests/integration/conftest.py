"""Integration test fixtures — local gateway app via ASGI test client.

Patches the heavy dependencies (SentenceTransformer, OpenRouter) so tests
run fast without model downloads or API keys.
"""

import hashlib
from unittest.mock import patch

import httpx
import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Lightweight embedder (no SentenceTransformer model download)
# ---------------------------------------------------------------------------


class _FakeEmbedder:
    """Deterministic 768-dim embedder that uses SHA-256 hashing."""

    def __init__(self, *args, **kwargs):
        self.dim = 768

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_embed(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        return self._hash_embed(text)

    def _hash_embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        rng = np.random.RandomState(int.from_bytes(h[:4], "big"))
        vec = rng.randn(self.dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


# ---------------------------------------------------------------------------
# Lightweight narrator (no OpenRouter API calls)
# ---------------------------------------------------------------------------


class _FakeNarrator:
    """Returns deterministic placeholder narratives without calling OpenRouter."""

    async def generate_hop(
        self,
        destination_node_id: str,
        player_path: list[str],
        prior_narrative: str,
        retrieved_chunks: list[dict],
        adjacent_nodes: list[str] | None = None,
    ) -> dict:
        adj = adjacent_nodes or []
        cards = [
            {
                "text": f"Explore {nid.replace('-', ' ')}",
                "destination_node_id": nid,
                "edge_weight_delta": 0.1,
                "thematic_color": "#6ee7b7",
            }
            for nid in adj[:3]
        ]
        return {
            "narrative_passage": (
                f"You arrive at {destination_node_id.replace('-', ' ').title()}. "
                f"The knowledge here connects to {len(adj)} neighbouring domains."
            ),
            "choice_cards": cards,
            "knowledge_synthesis": f"Synthesis for {destination_node_id}",
        }


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def app():
    """Create the dev gateway app with fake embedder and narrator."""
    with (
        patch("orchestrator.gateway.Embedder", _FakeEmbedder),
        patch("orchestrator.gateway._LocalNarrator", _FakeNarrator),
    ):
        from orchestrator.gateway import create_dev_app

        yield create_dev_app()


@pytest.fixture
async def client(app) -> httpx.AsyncClient:
    """ASGI test client — no network I/O, all in-process."""
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
