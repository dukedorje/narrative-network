"""Tests for orchestrator.unbrowse — UnbrowseClient stub and mocked API."""

from __future__ import annotations

import pytest
import respx
import httpx

from orchestrator.unbrowse import UnbrowseClient, UnbrowseResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> UnbrowseClient:
    """No-op client — no API key."""
    return UnbrowseClient(api_key="", base_url="https://unbrowse.test", timeout_s=5.0)


@pytest.fixture
def keyed_client() -> UnbrowseClient:
    """Client with fake key for mocked HTTP tests."""
    return UnbrowseClient(api_key="ub-key-123", base_url="https://unbrowse.test", timeout_s=5.0)


# ---------------------------------------------------------------------------
# Stub mode (no API key)
# ---------------------------------------------------------------------------


class TestStubMode:
    async def test_fetch_context_returns_empty(self, client):
        results = await client.fetch_context("quantum entanglement")
        assert results == []

    async def test_validate_domain_coverage_returns_zero(self, client):
        score = await client.validate_domain_coverage("astrophysics", "astro-01")
        assert score == 0.0

    async def test_fetch_node_enrichment_returns_empty_string(self, client):
        text = await client.fetch_node_enrichment("node-1", "physics", {})
        assert text == ""


# ---------------------------------------------------------------------------
# format_for_prompt
# ---------------------------------------------------------------------------


class TestFormatForPrompt:
    def test_empty_results(self, client):
        assert client.format_for_prompt([]) == ""

    def test_single_result(self, client):
        r = UnbrowseResult(
            query="test",
            url="https://example.com",
            content="some content here",
            source_type="web_page",
            confidence=0.9,
        )
        output = client.format_for_prompt([r])
        assert "[External Context via Unbrowse]" in output
        assert "example.com" in output
        assert "some content" in output

    def test_no_url_falls_back_to_unknown(self, client):
        r = UnbrowseResult(
            query="test", url=None, content="content", source_type="search_result", confidence=0.5
        )
        output = client.format_for_prompt([r])
        assert "unknown" in output

    def test_max_chars_respected(self, client):
        results = [
            UnbrowseResult(
                query="q",
                url=f"https://site{i}.com",
                content="x" * 500,
                source_type="web_page",
                confidence=0.8,
            )
            for i in range(3)
        ]
        output = client.format_for_prompt(results, max_chars=200)
        assert len(output) < 500  # shouldn't blow up


# ---------------------------------------------------------------------------
# Mocked API
# ---------------------------------------------------------------------------


class TestMockedAPI:
    @respx.mock
    async def test_fetch_context_success(self, keyed_client):
        respx.post("https://unbrowse.test/v1/context").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://wiki.example.com/quantum",
                            "content": "Quantum entanglement is a phenomenon...",
                            "source_type": "web_page",
                            "confidence": 0.92,
                        }
                    ]
                },
            )
        )
        results = await keyed_client.fetch_context("quantum entanglement", node_id="physics-01")
        assert len(results) == 1
        assert results[0].url == "https://wiki.example.com/quantum"
        assert results[0].confidence == pytest.approx(0.92)
        assert results[0].source_type == "web_page"

    @respx.mock
    async def test_fetch_context_http_error_returns_empty(self, keyed_client):
        respx.post("https://unbrowse.test/v1/context").mock(
            return_value=httpx.Response(429, json={"error": "rate limited"})
        )
        results = await keyed_client.fetch_context("any query")
        assert results == []

    @respx.mock
    async def test_fetch_context_network_error_returns_empty(self, keyed_client):
        respx.post("https://unbrowse.test/v1/context").mock(
            side_effect=httpx.ConnectError("timeout")
        )
        results = await keyed_client.fetch_context("any query")
        assert results == []

    @respx.mock
    async def test_validate_domain_coverage_averages_confidence(self, keyed_client):
        respx.post("https://unbrowse.test/v1/context").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"url": "u1", "content": "c1", "source_type": "web_page", "confidence": 0.8},
                        {"url": "u2", "content": "c2", "source_type": "web_page", "confidence": 0.6},
                    ]
                },
            )
        )
        score = await keyed_client.validate_domain_coverage("machine learning", "ml-01")
        assert score == pytest.approx(0.7)

    @respx.mock
    async def test_fetch_node_enrichment_joins_results(self, keyed_client):
        respx.post("https://unbrowse.test/v1/context").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"url": "u1", "content": "first chunk", "source_type": "web_page", "confidence": 0.9},
                        {"url": "u2", "content": "second chunk", "source_type": "web_page", "confidence": 0.7},
                    ]
                },
            )
        )
        text = await keyed_client.fetch_node_enrichment("node-1", "physics", {"description": "quantum"})
        assert "first chunk" in text
        assert "second chunk" in text

    @respx.mock
    async def test_empty_api_results(self, keyed_client):
        respx.post("https://unbrowse.test/v1/context").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        results = await keyed_client.fetch_context("obscure query")
        assert results == []
