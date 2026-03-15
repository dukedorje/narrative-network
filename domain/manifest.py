"""Domain manifest — declares a miner's knowledge domain.

The manifest is pinned to IPFS; only the CID is stored on-chain
via subtensor.set_commitment().
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DomainManifest:
    """A miner's declaration of their knowledge domain."""

    spec_version: str
    node_id: str
    display_label: str
    domain: str
    narrative_persona: str  # max 500 chars
    narrative_style: str  # max 200 chars
    adjacent_nodes: list[str]  # 1-4 node IDs
    centroid_embedding_cid: str  # IPFS CID of .npy file
    corpus_root_hash: str  # Merkle root of corpus chunks
    chunk_count: int  # minimum 10
    min_stake_tao: float
    created_at_epoch: int
    miner_hotkey: str
    manifest_cid: str = ""  # set after IPFS publish


@dataclass
class EdgeProposal:
    """A proposed edge from this node to an existing node."""

    target_node_id: str
    proposed_weight: float  # bounded; new nodes can't enter as dominant hubs
    edge_label: str = ""
