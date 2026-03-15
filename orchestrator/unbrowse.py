"""Unbrowse.ai client — external web context for queries not covered by the graph.

When corpus retrieval or graph traversal scores fall below threshold, the
UnbrowseClient fetches live web context from unbrowse.ai to supplement
in-graph knowledge.

Integration points:
- DomainMiner._forward: corpus fallback when domain_similarity < UNBROWSE_CORPUS_THRESHOLD
- NarrativeMiner._forward: enrich hop context with live web snippets
- IntegrationManager.enqueue: pre-fetch node enrichment during foreshadowing
- ProposalSubmitter.submit: validate domain coverage for ADD_NODE proposals
- Gateway POST /enter: ground query when no miner responds adequately
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

from subnet.config import UNBROWSE_API_URL, UNBROWSE_TIMEOUT_S, UNBROWSE_CORPUS_THRESHOLD

log = logging.getLogger(__name__)

_UNBROWSE_API_KEY = os.environ.get("UNBROWSE_API_KEY", "")


@dataclass
class UnbrowseResult:
    """Result of an Unbrowse context fetch.

    Attributes:
        query: Original query string.
        url: Source URL (if available).
        content: Extracted text content.
        source_type: "web_page" | "search_result" | "action_result"
        confidence: Relevance confidence 0.0–1.0.
    """

    query: str
    url: str | None
    content: str
    source_type: str
    confidence: float


class UnbrowseClient:
    """Async client for the Unbrowse.ai web context API.

    Serves as the data/action layer for any context not directly accessible
    via the knowledge graph. Provides non-blocking fallback — all errors are
    logged and return empty results so the main flow is never blocked.

    Usage:
        client = UnbrowseClient()
        results = await client.fetch_context("quantum entanglement", node_id="physics-01")
        # inject results into miner prompt or corpus
    """

    def __init__(
        self,
        api_key: str = _UNBROWSE_API_KEY,
        base_url: str = UNBROWSE_API_URL,
        timeout_s: float = UNBROWSE_TIMEOUT_S,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout_s,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def fetch_context(
        self,
        query: str,
        node_id: str | None = None,
        max_results: int = 3,
    ) -> list[UnbrowseResult]:
        """Fetch web context relevant to *query*.

        If *node_id* is given, it scopes the search to that knowledge domain.
        Returns up to *max_results* results ordered by relevance.
        Falls back to [] on any error — never raises.
        """
        if not self.api_key:
            log.debug("Unbrowse: no API key configured — skipping external fetch")
            return []

        payload: dict = {"query": query, "max_results": max_results}
        if node_id:
            payload["scope"] = node_id

        try:
            client = self._get_client()
            response = await client.post(f"{self.base_url}/v1/context", json=payload)
            response.raise_for_status()
            data = response.json()
            results = [
                UnbrowseResult(
                    query=query,
                    url=item.get("url"),
                    content=item.get("content", ""),
                    source_type=item.get("source_type", "web_page"),
                    confidence=float(item.get("confidence", 0.5)),
                )
                for item in data.get("results", [])
            ]
            log.info(
                "Unbrowse: %d results for query=%r node=%s",
                len(results),
                query[:60],
                node_id or "none",
            )
            return results
        except httpx.HTTPStatusError as exc:
            log.warning("Unbrowse HTTP %d: %s", exc.response.status_code, exc)
        except Exception as exc:
            log.warning("Unbrowse fetch error: %s", exc)
        return []

    async def validate_domain_coverage(self, domain: str, node_id: str) -> float:
        """Return a 0–1 confidence score for how well Unbrowse covers a proposed domain.

        Used during ADD_NODE proposal validation to verify the domain has sufficient
        real-world content to justify a knowledge graph node.
        """
        results = await self.fetch_context(
            query=f"knowledge domain overview: {domain}",
            node_id=node_id,
            max_results=5,
        )
        if not results:
            return 0.0
        return sum(r.confidence for r in results) / len(results)

    async def fetch_node_enrichment(
        self,
        node_id: str,
        domain: str,
        metadata: dict,
    ) -> str:
        """Fetch rich external context for a node during integration foreshadowing.

        Returns concatenated content from top results, suitable for seeding miner
        corpus or grounding narrative generation. Called by IntegrationManager.enqueue.
        """
        query = metadata.get("description") or domain
        results = await self.fetch_context(query=query, node_id=node_id, max_results=5)
        if not results:
            return ""
        return "\n\n".join(
            f"[{r.source_type}] {r.url or 'unknown'}\n{r.content}" for r in results
        )

    def format_for_prompt(self, results: list[UnbrowseResult], max_chars: int = 800) -> str:
        """Format Unbrowse results as a compact string for injection into LLM prompts."""
        if not results:
            return ""
        lines = ["[External Context via Unbrowse]"]
        total = 0
        for r in results:
            snippet = r.content[: max_chars // len(results)]
            entry = f"- ({r.source_type}) {r.url or 'unknown'}: {snippet}"
            lines.append(entry)
            total += len(entry)
            if total >= max_chars:
                break
        return "\n".join(lines)
