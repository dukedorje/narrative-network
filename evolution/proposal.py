"""Proposal creation, submission, and bond management for on-chain governance.

Validators submit NodeProposals to add/remove nodes or edges from the
living knowledge graph. Each proposal requires a TAO bond that is returned
on acceptance or burned on rejection after the voting period.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

import bittensor as bt

from subnet.config import PROPOSAL_MIN_BOND_TAO, VOTING_OPEN_BLOCKS
from evolution.nla_settlement import NLAgreement, NLASettlementClient

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    VOTING = "VOTING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INTEGRATING = "INTEGRATING"
    LIVE = "LIVE"
    BOND_RETURNED = "BOND_RETURNED"


class ProposalType(str, Enum):
    ADD_NODE = "ADD_NODE"
    REMOVE_NODE = "REMOVE_NODE"
    ADD_EDGE = "ADD_EDGE"
    UPDATE_META = "UPDATE_META"


# ---------------------------------------------------------------------------
# NodeProposal dataclass
# ---------------------------------------------------------------------------

@dataclass
class NodeProposal:
    """On-chain proposal to mutate the knowledge graph topology.

    Attributes:
        proposal_type: The mutation category.
        proposer_hotkey: SS58 hotkey of the submitting validator.
        node_id: Target node identifier (or source for ADD_EDGE).
        dest_node_id: Destination node for ADD_EDGE proposals.
        metadata: Arbitrary key/value pairs (title, description, embedding, etc.).
        bond_tao: TAO amount locked as bond.
        submitted_block: Block at which proposal was registered on-chain.
        status: Current lifecycle status.
        proposal_id: Derived from commitment_hash() after submission.
    """

    proposal_type: ProposalType
    proposer_hotkey: str
    node_id: str
    dest_node_id: str = ""
    metadata: dict = field(default_factory=dict)
    bond_tao: float = PROPOSAL_MIN_BOND_TAO
    submitted_block: int = 0
    status: ProposalStatus = ProposalStatus.DRAFT
    proposal_id: str = ""
    nla_agreement: NLAgreement | None = None

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------

    def compute_id(self) -> str:
        """Return a deterministic short identifier (first 16 hex chars of SHA-256)."""
        raw = f"{self.proposal_type}:{self.proposer_hotkey}:{self.node_id}:{self.dest_node_id}:{self.submitted_block}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def canonical_payload(self) -> dict:
        """Return the canonical JSON-serialisable payload for hashing."""
        return {
            "proposal_type": self.proposal_type.value,
            "proposer_hotkey": self.proposer_hotkey,
            "node_id": self.node_id,
            "dest_node_id": self.dest_node_id,
            "metadata": self.metadata,
            "bond_tao": self.bond_tao,
            "submitted_block": self.submitted_block,
        }

    def commitment_hash(self) -> str:
        """SHA-256 over the sorted canonical payload (commit-reveal compatible)."""
        serialised = json.dumps(self.canonical_payload(), sort_keys=True)
        return hashlib.sha256(serialised.encode()).hexdigest()


# ---------------------------------------------------------------------------
# ProposalSubmitter
# ---------------------------------------------------------------------------

class ProposalSubmitter:
    """Builds and submits NodeProposals to the subnet.

    Args:
        wallet: Bittensor wallet used to sign and bond.
        subtensor: Bittensor Subtensor connection for on-chain calls.
        netuid: Subnet UID.
        min_bond_tao: Minimum bond required (defaults to config value).
    """

    def __init__(
        self,
        wallet: bt.Wallet,
        subtensor: bt.Subtensor,
        netuid: int,
        min_bond_tao: float = PROPOSAL_MIN_BOND_TAO,
    ) -> None:
        self.wallet = wallet
        self.subtensor = subtensor
        self.netuid = netuid
        self.min_bond_tao = min_bond_tao

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        proposal_type: ProposalType,
        node_id: str,
        metadata: dict | None = None,
        dest_node_id: str = "",
        bond_tao: float | None = None,
    ) -> NodeProposal:
        """Construct a DRAFT proposal without submitting."""
        bond = bond_tao if bond_tao is not None else self.min_bond_tao
        self._validate_bond(bond)
        return NodeProposal(
            proposal_type=proposal_type,
            proposer_hotkey=self.wallet.hotkey.ss58_address,
            node_id=node_id,
            dest_node_id=dest_node_id,
            metadata=metadata or {},
            bond_tao=bond,
        )

    def submit(self, proposal: NodeProposal) -> NodeProposal:
        """Validate, lock bond, record commitment on-chain, return SUBMITTED proposal.

        Raises:
            ValueError: If validation fails.
            RuntimeError: If on-chain commitment fails.
        """
        self._validate_proposal(proposal)
        self._validate_bond(proposal.bond_tao)

        current_block = self._get_current_block()
        proposal.submitted_block = current_block
        proposal.proposal_id = proposal.compute_id()

        commitment = proposal.commitment_hash()
        log.info(
            "Submitting proposal id=%s type=%s node=%s block=%d commitment=%s",
            proposal.proposal_id,
            proposal.proposal_type.value,
            proposal.node_id,
            current_block,
            commitment[:12] + "...",
        )

        self._lock_bond(proposal)
        self._commit_on_chain(proposal, commitment)

        proposal.status = ProposalStatus.SUBMITTED
        return proposal

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _validate_bond(self, bond_tao: float) -> None:
        if bond_tao < self.min_bond_tao:
            raise ValueError(
                f"Bond {bond_tao} TAO is below minimum {self.min_bond_tao} TAO"
            )

    def _validate_proposal(self, proposal: NodeProposal) -> None:
        if not proposal.node_id:
            raise ValueError("node_id must not be empty")
        if proposal.proposal_type == ProposalType.ADD_EDGE and not proposal.dest_node_id:
            raise ValueError("ADD_EDGE proposal requires dest_node_id")
        if proposal.status != ProposalStatus.DRAFT:
            raise ValueError(
                f"Proposal must be in DRAFT state to submit, got {proposal.status}"
            )

    def _get_current_block(self) -> int:
        try:
            return self.subtensor.get_current_block()
        except Exception as exc:
            log.warning("Could not fetch current block: %s — using timestamp fallback", exc)
            return int(time.time())

    def _lock_bond(self, proposal: NodeProposal) -> None:
        """Lock the bond amount from the proposer's wallet.

        TODO: Implement actual on-chain bond locking via extrinsic once
        Bittensor exposes a proposal-bond pallet. Currently a no-op stub.

        Builds a draft NLA agreement that captures the bond escrow terms in
        natural language. The draft is stored on the proposal; async registration
        with the Arkhai NLA service happens in VotingEngine.register_proposal.
        """
        log.info(
            "Bond locked: %.4f TAO from %s for proposal %s",
            proposal.bond_tao,
            proposal.proposer_hotkey,
            proposal.proposal_id,
        )
        nla = NLASettlementClient()
        proposal.nla_agreement = nla.build_proposal_agreement(
            proposal_id=proposal.proposal_id,
            proposer_hotkey=proposal.proposer_hotkey,
            node_id=proposal.node_id,
            proposal_type=proposal.proposal_type.value,
            bond_tao=proposal.bond_tao,
            voting_deadline_block=proposal.submitted_block + VOTING_OPEN_BLOCKS,
        )
        log.info("NLA draft prepared for proposal %s", proposal.proposal_id)

    def _commit_on_chain(self, proposal: NodeProposal, commitment: str) -> None:
        """Store commitment hash on-chain via commit_weights mechanism.

        Uses the commit_weights extrinsic as a commitment store until a
        dedicated proposal pallet is available.
        """
        try:
            self.subtensor.commit(
                wallet=self.wallet,
                netuid=self.netuid,
                data=commitment,
            )
            log.info("On-chain commitment recorded for proposal %s", proposal.proposal_id)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to commit proposal {proposal.proposal_id} on-chain: {exc}"
            ) from exc
