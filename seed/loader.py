"""Seed topology loader — reads topology.yaml and populates GraphStore."""

from __future__ import annotations

from pathlib import Path

import yaml

from subnet.graph_store import GraphStore


_SEED_DIR = Path(__file__).parent
_DEFAULT_TOPOLOGY = _SEED_DIR / "topology.yaml"
_CORPUS_BASE = Path(__file__).parent.parent / "docs" / "corpora" / "quantum_mechanics"


def load_topology(
    topology_path: str | Path = _DEFAULT_TOPOLOGY,
    corpus_base: str | Path = _CORPUS_BASE,
    graph_store: GraphStore | None = None,
) -> tuple[GraphStore, dict[str, list[Path]]]:
    """Load seed topology into a GraphStore.

    Returns:
        (graph_store, corpus_map) where corpus_map is {node_id: [Path, ...]}.
    """
    topology_path = Path(topology_path)
    corpus_base = Path(corpus_base)

    with open(topology_path) as f:
        topo = yaml.safe_load(f)

    if graph_store is None:
        graph_store = GraphStore(db_path=None)

    # Load nodes
    nodes_data = []
    corpus_map: dict[str, list[Path]] = {}

    for node_def in topo["nodes"]:
        node_id = node_def["node_id"]
        nodes_data.append({
            "node_id": node_id,
            "state": node_def.get("state", "Live"),
            "metadata": node_def.get("metadata", {}),
        })
        # Map corpus files
        corpus_files = node_def.get("corpus_files", [])
        corpus_map[node_id] = [corpus_base / fname for fname in corpus_files]

    # Load edges
    edges_data = []
    for edge_def in topo["edges"]:
        edges_data.append({
            "source_id": edge_def["source_id"],
            "dest_id": edge_def["dest_id"],
            "weight": edge_def.get("weight", 1.0),
        })

    graph_store.bulk_load(nodes_data, edges_data)

    return graph_store, corpus_map


def get_node_ids(topology_path: str | Path = _DEFAULT_TOPOLOGY) -> list[str]:
    """Return list of node IDs from topology file."""
    with open(topology_path) as f:
        topo = yaml.safe_load(f)
    return [n["node_id"] for n in topo["nodes"]]
