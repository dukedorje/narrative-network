"""Arkhai traversal arbiter — validates hops and filters next-hop candidates.

When a player selects a hop, this module registers a StringObligation NLA
with the Arkhai service describing the traversal demand. The Alkahest arbiter
evaluates:

  1. Whether the selected hop is a valid conceptual continuation.
  2. Which neighbouring nodes are epistemically appropriate next steps given
     the player's accumulated path.

The arbiter response (approved_candidates) replaces the raw graph neighbour
list so choice cards reflect meaningful forward movement, not just adjacency.

Falls back to the full neighbour list on any error — traversal is never
blocked by external service availability.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

from subnet.config import NLA_ENDPOINT, NLA_CHAIN

log = logging.getLogger(__name__)

_NLA_API_KEY = os.environ.get("NLA_API_KEY", "")


@dataclass
class HopArbiterResult:
    """Result from the Arkhai traversal arbiter.

    Attributes:
        approved: Whether the selected hop is valid.
        filtered_candidates: Arbiter-approved subset of the raw candidate list.
        reasoning: Natural language explanation from the arbiter.
        arbiter_uid: EAS attestation UID of the arbiter check (if on-chain).
    """

    approved: bool
    filtered_candidates: list[str]
    reasoning: str = ""
    arbiter_uid: str = ""


class TraversalArbiter:
    """Calls Arkhai NLA to arbitrate hop validity and filter next-hop candidates.

    The arbiter receives a natural language demand describing:
    - The player's accumulated traversal path
    - The selected hop (source_node → dest_node)
    - The raw candidate next nodes (graph neighbours of dest_node)

    It returns which candidates represent meaningful forward steps given the
    player's thematic trajectory, excluding trivial cycles and off-thread jumps.

    All calls are non-blocking — failures fall back to the full candidate list.

    Usage:
        arbiter = TraversalArbiter()
        result = await arbiter.check_hop(
            session_id="abc",
            source_node="quantum-foundations",
            dest_node="thermodynamics",
            player_path=["quantum-foundations", "thermodynamics"],
            candidates=["relativity", "emergence", "chemical-bonding"],
            node_descriptions={...},
        )
        # result.filtered_candidates is the arbiter-approved subset
    """

    def __init__(
        self,
        api_key: str = _NLA_API_KEY,
        endpoint: str = NLA_ENDPOINT,
        chain: str = NLA_CHAIN,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.chain = chain
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=15.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _build_demand(
        self,
        session_id: str,
        source_node: str,
        dest_node: str,
        player_path: list[str],
        candidates: list[str],
        node_descriptions: dict[str, str],
    ) -> str:
        path_str = " → ".join(player_path) if player_path else source_node
        candidate_lines = "\n".join(
            f"  - {c}: {node_descriptions.get(c, c)}" for c in candidates
        )
        return (
            f"Traversal Hop Arbitration — Narrative Network Subnet 42\n\n"
            f"Session: {session_id}\n"
            f"Player path: {path_str}\n"
            f"Selected hop: {source_node} → {dest_node}\n"
            f"  Source: {node_descriptions.get(source_node, source_node)}\n"
            f"  Destination: {node_descriptions.get(dest_node, dest_node)}\n\n"
            f"Candidate next nodes (neighbours of {dest_node}):\n"
            f"{candidate_lines}\n\n"
            f"Arbiter demand:\n"
            f"1. Confirm that '{dest_node}' is a valid conceptual continuation "
            f"from '{source_node}'.\n"
            f"2. From the candidates above, return only those that represent "
            f"meaningful forward steps given the player's accumulated path.\n"
            f"3. Exclude candidates that create trivial cycles or diverge too far "
            f"from the thematic thread established by: {path_str}.\n\n"
            f"Arbiter: Alkahest StringObligation + Narrative Network graph edge weights.\n"
            f"Chain: {self.chain}"
        )

    async def check_hop(
        self,
        session_id: str,
        source_node: str,
        dest_node: str,
        player_path: list[str],
        candidates: list[str],
        node_descriptions: dict[str, str] | None = None,
    ) -> HopArbiterResult:
        """Arbitrate a hop and return the filtered candidate set.

        If NLA_API_KEY is absent or the service is unreachable, returns all
        candidates with approved=True so traversal is never blocked.
        """
        if not candidates:
            return HopArbiterResult(approved=True, filtered_candidates=[])

        if not self.api_key:
            log.debug("TraversalArbiter: no API key — returning all %d candidates", len(candidates))
            return HopArbiterResult(
                approved=True,
                filtered_candidates=candidates,
                reasoning="stub: no NLA_API_KEY configured",
            )

        demand = self._build_demand(
            session_id=session_id,
            source_node=source_node,
            dest_node=dest_node,
            player_path=player_path,
            candidates=candidates,
            node_descriptions=node_descriptions or {},
        )

        try:
            client = self._get_client()
            response = await client.post(
                f"{self.endpoint}/v1/arbitrate",
                json={
                    "demand": demand,
                    "chain": self.chain,
                    "candidates": candidates,
                    "metadata": {
                        "session_id": session_id,
                        "source_node": source_node,
                        "dest_node": dest_node,
                        "player_path": player_path,
                        "type": "traversal_hop",
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

            approved = data.get("approved", True)
            raw_filtered = data.get("approved_candidates", candidates)

            # Guarantee filtered is a subset of the original candidates
            candidate_set = set(candidates)
            filtered = [c for c in raw_filtered if c in candidate_set] or candidates

            log.info(
                "TraversalArbiter: session=%s hop=%s->%s approved=%s "
                "candidates=%d->%d uid=%s",
                session_id[:8],
                source_node,
                dest_node,
                approved,
                len(candidates),
                len(filtered),
                data.get("arbiter_uid", "")[:12],
            )
            return HopArbiterResult(
                approved=approved,
                filtered_candidates=filtered,
                reasoning=data.get("reasoning", ""),
                arbiter_uid=data.get("arbiter_uid", ""),
            )

        except Exception as exc:
            log.warning("TraversalArbiter error (non-blocking): %s", exc)
            return HopArbiterResult(
                approved=True,
                filtered_candidates=candidates,
                reasoning=f"fallback: {exc}",
            )
