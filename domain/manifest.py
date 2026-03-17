"""Domain manifest — declares a miner's knowledge domain.

The manifest is pinned to IPFS; only the CID is stored on-chain
via subtensor.set_commitment().
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


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

    def to_json(self) -> str:
        """Serialize manifest to JSON string."""
        return json.dumps({
            "spec_version": self.spec_version,
            "node_id": self.node_id,
            "display_label": self.display_label,
            "domain": self.domain,
            "narrative_persona": self.narrative_persona,
            "narrative_style": self.narrative_style,
            "adjacent_nodes": self.adjacent_nodes,
            "centroid_embedding_cid": self.centroid_embedding_cid,
            "corpus_root_hash": self.corpus_root_hash,
            "chunk_count": self.chunk_count,
            "min_stake_tao": self.min_stake_tao,
            "created_at_epoch": self.created_at_epoch,
            "miner_hotkey": self.miner_hotkey,
            "manifest_cid": self.manifest_cid,
        }, sort_keys=True)

    @classmethod
    def from_json(cls, data: str) -> "DomainManifest":
        """Deserialize manifest from JSON string."""
        d = json.loads(data)
        return cls(**d)


@dataclass
class EdgeProposal:
    """A proposed edge from this node to an existing node."""

    target_node_id: str
    proposed_weight: float  # bounded; new nodes can't enter as dominant hubs
    edge_label: str = ""


class ManifestStore:
    """Local manifest store (stub for IPFS).

    Stores full manifest JSON to local files keyed by content-hash CID.
    # TODO: Replace local store with IPFS pin
    """

    def __init__(self, data_dir: str = "./data") -> None:
        self._manifest_dir = Path(data_dir) / "manifests"
        self._manifest_dir.mkdir(parents=True, exist_ok=True)

    def save(self, manifest: DomainManifest) -> str:
        """Persist manifest locally and return its content-hash CID."""
        json_bytes = manifest.to_json().encode()
        cid = hashlib.sha256(json_bytes).hexdigest()
        manifest.manifest_cid = cid
        path = self._manifest_dir / f"{cid}.json"
        path.write_text(manifest.to_json())
        return cid

    def load(self, cid: str) -> DomainManifest | None:
        """Retrieve and deserialize a manifest by CID. Returns None if not found."""
        path = self._manifest_dir / f"{cid}.json"
        if not path.exists():
            return None
        return DomainManifest.from_json(path.read_text())
