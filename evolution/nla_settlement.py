"""Natural Language Agreement settlement for on-chain proposal governance.

Integrates with https://github.com/arkhai-io/natural-language-agreements
(Arkhai Alkahest protocol) to express and settle bond agreements on-chain.

Each NodeProposal generates an NLA that specifies:
  - Bond escrow conditions (who pays, how much)
  - Settlement trigger (vote outcome at block N)
  - Release terms (TAO returned on ACCEPTED, burned on REJECTED)
  - Arbiter (stake-weighted Yuma Consensus on netuid 42)

Attestations are recorded via EAS; all settlements are auditable on-chain.
All API calls are non-blocking — failures are logged and do not halt
the Bittensor proposal/voting flow.
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
class NLAgreement:
    """A natural language agreement registered with the Arkhai NLA service.

    Attributes:
        agreement_text: Human-readable agreement text (natural language spec).
        proposal_id: Narrative Network proposal ID this agreement covers.
        escrow_uid: EAS attestation UID of the on-chain escrow (post-registration).
        fulfillment_uid: EAS attestation UID after final settlement.
        status: "draft" | "registered" | "returned" | "burned"
    """

    agreement_text: str
    proposal_id: str
    escrow_uid: str = ""
    fulfillment_uid: str = ""
    status: str = "draft"
    metadata: dict = field(default_factory=dict)


@dataclass
class SettlementResult:
    """Result of an NLA settlement action."""

    proposal_id: str
    agreement_uid: str
    action: str  # "bond_returned" | "bond_burned"
    success: bool
    tx_hash: str = ""
    error: str = ""


class NLASettlementClient:
    """Client for the Arkhai Natural Language Agreements API.

    Bridges Narrative Network governance events (vote outcomes, integration
    milestones, node collapses) to on-chain settlement via Alkahest escrows.

    Agreement text is expressed in natural language; the Arkhai NLA service
    compiles it to Solidity escrow + arbiter contract interactions, with all
    state changes attested via EAS.

    All methods are non-blocking — errors log warnings and return gracefully.
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
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Agreement construction
    # ------------------------------------------------------------------

    def build_proposal_agreement(
        self,
        proposal_id: str,
        proposer_hotkey: str,
        node_id: str,
        proposal_type: str,
        bond_tao: float,
        voting_deadline_block: int,
    ) -> NLAgreement:
        """Construct the NLA for a node proposal bond escrow.

        The natural language text specifies the full escrow lifecycle:
        acceptance -> bond return, rejection -> bond burn, expiry -> bond return.
        This text is submitted to the Arkhai NLA service which resolves it
        to Alkahest BaseEscrowObligation + stake-weighted VotingArbiter.
        """
        text = (
            f"Proposal Bond Agreement — Narrative Network Subnet 42\n\n"
            f"Proposer: {proposer_hotkey}\n"
            f"Proposal ID: {proposal_id}\n"
            f"Action: {proposal_type} node '{node_id}'\n"
            f"Bond Amount: {bond_tao:.4f} TAO\n"
            f"Voting Deadline: Block {voting_deadline_block}\n\n"
            f"Terms:\n"
            f"- The proposer locks {bond_tao:.4f} TAO as a bond against this proposal.\n"
            f"- If a quorum of stake-weighted validators votes FOR this proposal before "
            f"block {voting_deadline_block}, the bond is returned to the proposer in full.\n"
            f"- If the proposal is REJECTED (quorum not met or majority AGAINST), "
            f"the bond is burned to the subnet treasury.\n"
            f"- If the proposal is not finalised by block {voting_deadline_block}, "
            f"the bond is automatically returned to the proposer.\n"
            f"Arbiter: Stake-weighted Yuma Consensus on Bittensor netuid 42."
        )
        return NLAgreement(
            agreement_text=text,
            proposal_id=proposal_id,
            metadata={
                "proposer_hotkey": proposer_hotkey,
                "node_id": node_id,
                "bond_tao": bond_tao,
                "voting_deadline_block": voting_deadline_block,
            },
        )

    def build_integration_agreement(
        self,
        proposal_id: str,
        node_id: str,
        proposer_hotkey: str,
        bond_tao: float,
        live_block: int,
    ) -> NLAgreement:
        """Build NLA for bond return on successful node integration."""
        text = (
            f"Node Integration Bond Return — Narrative Network Subnet 42\n\n"
            f"Node: {node_id}\n"
            f"Proposal: {proposal_id}\n"
            f"Owner: {proposer_hotkey}\n\n"
            f"Terms:\n"
            f"- Node '{node_id}' has completed the integration pipeline and is LIVE "
            f"at block {live_block} with a qualifying performance score.\n"
            f"- Bond of {bond_tao:.4f} TAO is returned to {proposer_hotkey}.\n"
            f"Arbiter: IntegrationManager automated pipeline "
            f"(RAMP phase score >= INTEGRATION_MIN_SCORE)."
        )
        return NLAgreement(
            agreement_text=text,
            proposal_id=proposal_id,
            metadata={
                "proposer_hotkey": proposer_hotkey,
                "node_id": node_id,
                "bond_tao": bond_tao,
                "live_block": live_block,
            },
        )

    def build_collapse_agreement(
        self,
        node_id: str,
        proposer_hotkey: str,
        bond_tao: float,
        epoch: int,
        reason: str,
    ) -> NLAgreement:
        """Build NLA for slash-on-collapse settlement."""
        text = (
            f"Node Collapse Penalty Agreement — Narrative Network Subnet 42\n\n"
            f"Node: {node_id}\n"
            f"Owner: {proposer_hotkey}\n"
            f"Epoch: {epoch}\n"
            f"Reason: {reason}\n\n"
            f"Terms:\n"
            f"- Node '{node_id}' has collapsed due to sustained underperformance.\n"
            f"- Remaining bond of {bond_tao:.4f} TAO is forfeit and burned to the subnet treasury.\n"
            f"- The node is removed from the live knowledge graph immediately.\n"
            f"Arbiter: PruningEngine automated state machine "
            f"(consecutive DECAYING epochs >= collapse_consecutive threshold)."
        )
        return NLAgreement(
            agreement_text=text,
            proposal_id=f"collapse:{node_id}:{epoch}",
            metadata={
                "proposer_hotkey": proposer_hotkey,
                "node_id": node_id,
                "bond_tao": bond_tao,
                "epoch": epoch,
                "reason": reason,
            },
        )

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    async def register(self, agreement: NLAgreement) -> NLAgreement:
        """Register an NLA with the Arkhai service and record the escrow UID.

        On success, sets agreement.escrow_uid and status = "registered".
        On failure, sets status = "draft" and logs a warning — the proposal
        flow continues regardless so Bittensor operations are never blocked.
        """
        if not self.api_key:
            log.debug("NLA: no API key configured — operating in stub mode")
            agreement.status = "draft"
            return agreement

        try:
            client = self._get_client()
            response = await client.post(
                f"{self.endpoint}/v1/agreements",
                json={
                    "text": agreement.agreement_text,
                    "chain": self.chain,
                    "metadata": {"proposal_id": agreement.proposal_id, **agreement.metadata},
                },
            )
            response.raise_for_status()
            data = response.json()
            agreement.escrow_uid = data.get("escrow_uid", "")
            agreement.status = "registered"
            log.info(
                "NLA registered: proposal=%s escrow_uid=%s",
                agreement.proposal_id,
                (agreement.escrow_uid[:12] + "...") if agreement.escrow_uid else "none",
            )
        except Exception as exc:
            log.warning("NLA registration failed (non-blocking): %s", exc)
            agreement.status = "draft"
        return agreement

    async def settle(
        self,
        agreement: NLAgreement,
        action: str,  # "return" | "burn"
        proposal_id: str,
        bond_tao: float,
        proposer_hotkey: str,
    ) -> SettlementResult:
        """Settle an NLA — release or burn the bond via Alkahest escrow.

        Maps to:
        - "return" -> _releaseEscrow -> collectEscrow to proposer
        - "burn"   -> _returnEscrow expired path -> send to treasury

        Falls back to log-only stub if the API key is absent or unreachable.
        """
        action_label = f"bond_{'returned' if action == 'return' else 'burned'}"

        if not self.api_key or not agreement.escrow_uid:
            log.info(
                "NLA settle (stub): proposal=%s action=%s bond=%.4f TAO to %s",
                proposal_id,
                action,
                bond_tao,
                proposer_hotkey if action == "return" else "treasury",
            )
            return SettlementResult(
                proposal_id=proposal_id,
                agreement_uid=agreement.escrow_uid or "stub",
                action=action_label,
                success=True,
            )

        try:
            client = self._get_client()
            response = await client.post(
                f"{self.endpoint}/v1/agreements/{agreement.escrow_uid}/settle",
                json={
                    "action": action,
                    "recipient": proposer_hotkey if action == "return" else "treasury",
                    "amount_tao": bond_tao,
                    "chain": self.chain,
                },
            )
            response.raise_for_status()
            data = response.json()
            fulfillment_uid = data.get("fulfillment_uid", "")
            agreement.fulfillment_uid = fulfillment_uid
            agreement.status = "returned" if action == "return" else "burned"
            log.info(
                "NLA settled: proposal=%s action=%s fulfillment=%s tx=%s",
                proposal_id,
                action,
                (fulfillment_uid[:12] + "...") if fulfillment_uid else "none",
                data.get("tx_hash", "")[:12],
            )
            return SettlementResult(
                proposal_id=proposal_id,
                agreement_uid=fulfillment_uid,
                action=action_label,
                success=True,
                tx_hash=data.get("tx_hash", ""),
            )
        except Exception as exc:
            log.error("NLA settlement error: %s", exc)
            return SettlementResult(
                proposal_id=proposal_id,
                agreement_uid=agreement.escrow_uid,
                action=action_label,
                success=False,
                error=str(exc),
            )
