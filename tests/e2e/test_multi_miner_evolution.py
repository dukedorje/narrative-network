"""End-to-end test: multi-miner evolution lifecycle.

Demonstrates: node registration via manifest -> scoring -> pruning
using the full LocalValidator pipeline with mock infrastructure.

Tests are component-level (GraphStore, PruningEngine, ManifestStore,
MockSubtensor) rather than running the full LocalValidator epoch loop,
which requires real embeddings and a seeded topology loader. This keeps
the suite fast and hermetic.
"""

import pytest

from domain.manifest import DomainManifest, ManifestStore
from evolution.pruning import EpochScore, PrunePhase, PruningEngine
from subnet.graph_store import GraphStore
from subnet.harness import (
    FakeEmbedder,
    create_local_network,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def multi_miner_setup(tmp_path):
    """Create a 5-miner local network with manifest commitments pre-loaded."""
    n_miners = 5
    node_ids = [f"domain-{i}" for i in range(n_miners)]

    harness = create_local_network(n_miners=n_miners, graph_node_ids=node_ids)

    # Publish manifests for each miner and commit CIDs on MockSubtensor
    manifest_store = ManifestStore(data_dir=str(tmp_path / "manifests"))

    manifests: dict[int, DomainManifest] = {}
    for i in range(n_miners):
        uid = i + 1  # miner UIDs start at 1; UID 0 = validator
        manifest = DomainManifest(
            spec_version="1.0",
            node_id=node_ids[i],
            display_label=f"Domain {i}",
            domain=f"test-domain-{i}",
            narrative_persona="neutral",
            narrative_style="academic",
            adjacent_nodes=[nid for nid in node_ids if nid != node_ids[i]][:2],
            centroid_embedding_cid=f"centroid-cid-{i}",
            corpus_root_hash=f"root-hash-{i}",
            chunk_count=50,
            min_stake_tao=1.0,
            created_at_epoch=0,
            miner_hotkey=f"miner-{i}-hotkey",
        )
        cid = manifest_store.save(manifest)
        harness["subtensor"].set_commitment(netuid=0, uid=uid, data=cid)
        manifests[uid] = manifest

    return {
        **harness,
        "node_ids": node_ids,
        "manifest_store": manifest_store,
        "manifests": manifests,
        "tmp_path": tmp_path,
        "n_miners": n_miners,
    }


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestMultiMinerEvolution:
    """Multi-miner e2e tests: registration -> scoring -> pruning."""

    # ------------------------------------------------------------------
    # Test 1: Manifest registration round-trip via MockSubtensor
    # ------------------------------------------------------------------

    def test_manifest_registration_and_graph_store(self, multi_miner_setup):
        """Manifests committed on-chain can be loaded and registered in graph store."""
        setup = multi_miner_setup
        gs = GraphStore(db_path=str(setup["tmp_path"] / "reg_test.db"))
        manifest_store = setup["manifest_store"]
        subtensor = setup["subtensor"]
        n_miners = setup["n_miners"]

        uid_to_node_id: dict[int, str] = {}
        for uid in range(1, n_miners + 1):
            cid = subtensor.get_commitment(netuid=0, uid=uid)
            assert cid is not None, f"UID {uid} has no commitment"

            manifest = manifest_store.load(cid)
            assert manifest is not None, f"Manifest for CID {cid[:16]} not found"
            assert manifest.node_id == f"domain-{uid - 1}"

            uid_to_node_id[uid] = manifest.node_id
            gs.add_node(manifest.node_id, state="Live", metadata={"uid": uid})

        live_nodes = gs.get_live_node_ids()
        assert len(live_nodes) == n_miners
        for i in range(n_miners):
            assert f"domain-{i}" in live_nodes

    # ------------------------------------------------------------------
    # Test 2: uid -> node_id mapping end-to-end
    # ------------------------------------------------------------------

    def test_uid_to_node_id_mapping(self, multi_miner_setup):
        """CID lookup -> manifest.node_id gives the correct domain identifier."""
        setup = multi_miner_setup
        subtensor = setup["subtensor"]
        manifest_store = setup["manifest_store"]
        n_miners = setup["n_miners"]

        uid_to_node_id: dict[int, str] = {}
        for uid in range(1, n_miners + 1):
            cid = subtensor.get_commitment(netuid=0, uid=uid)
            manifest = manifest_store.load(cid)
            assert manifest is not None
            uid_to_node_id[uid] = manifest.node_id

        # Each UID maps to exactly the expected domain node
        for uid in range(1, n_miners + 1):
            expected_node_id = f"domain-{uid - 1}"
            assert uid_to_node_id[uid] == expected_node_id, (
                f"UID {uid}: expected {expected_node_id!r}, got {uid_to_node_id[uid]!r}"
            )

        # No two UIDs should map to the same node
        node_ids = list(uid_to_node_id.values())
        assert len(set(node_ids)) == len(node_ids), "Duplicate node_id assignments detected"

    # ------------------------------------------------------------------
    # Test 3: Graph persistence across GraphStore restart
    # ------------------------------------------------------------------

    def test_graph_persistence_across_restart(self, multi_miner_setup):
        """Graph nodes and edges survive a GraphStore restart via KuzuDB."""
        setup = multi_miner_setup
        db_path = str(setup["tmp_path"] / "persist.db")

        # First instance: write nodes and an edge
        gs1 = GraphStore(db_path=db_path)
        gs1.add_node("persistent-node", state="Live", metadata={"test": True})
        gs1.add_node("other-node", state="Live", metadata={})
        gs1.upsert_edge("persistent-node", "other-node", weight=2.5)

        # Delete reference and create new instance from same path
        del gs1

        gs2 = GraphStore(db_path=db_path)

        node = gs2.get_node("persistent-node")
        assert node is not None, "Node did not survive restart"
        assert node.state == "Live"

        edges = gs2.get_all_edges()
        assert any(
            e.source_id == "persistent-node" and e.dest_id == "other-node"
            for e in edges
        ), "Edge did not survive restart"

        edge = next(
            e for e in edges
            if e.source_id == "persistent-node" and e.dest_id == "other-node"
        )
        assert abs(edge.weight - 2.5) < 1e-6, f"Edge weight not preserved: {edge.weight}"

    # ------------------------------------------------------------------
    # Test 4: set_node_state persists through restart
    # ------------------------------------------------------------------

    def test_node_state_update_persists(self, multi_miner_setup):
        """set_node_state("Pruned") survives a GraphStore restart."""
        setup = multi_miner_setup
        db_path = str(setup["tmp_path"] / "state_persist.db")

        gs1 = GraphStore(db_path=db_path)
        gs1.add_node("target-node", state="Live")
        gs1.set_node_state("target-node", "Pruned")
        del gs1

        gs2 = GraphStore(db_path=db_path)
        node = gs2.get_node("target-node")
        assert node is not None
        assert node.state == "Pruned", f"Expected Pruned, got {node.state}"

    # ------------------------------------------------------------------
    # Test 5: Pruning lifecycle — healthy vs. low-quality node
    # ------------------------------------------------------------------

    def test_pruning_lifecycle_healthy_vs_low_quality(self, multi_miner_setup):
        """Low-quality node collapses; high-quality node stays HEALTHY."""
        # Use small window/collapse values so the test runs in ~10 iterations
        engine = PruningEngine(
            window_size=4,
            collapse_consecutive=3,
            warning_threshold=0.35,
            decay_threshold=0.20,
            min_traversals=1,
            nla_client=None,
        )
        engine.register_node("domain-0")  # high-quality
        engine.register_node("domain-1")  # low-quality

        # Push enough epochs for domain-1 to reach COLLAPSED
        # window_size=4, collapse_consecutive=3 means after 4 pushes with score<0.20
        # the window is full and consecutive_below will be >= 3.
        for epoch in range(6):
            engine.push_scores(epoch, {
                "domain-0": EpochScore(
                    epoch=epoch, node_id="domain-0", score=0.9, traversal_count=5
                ),
                "domain-1": EpochScore(
                    epoch=epoch, node_id="domain-1", score=0.05, traversal_count=5
                ),
            })
            engine.process_epoch(epoch)

        state_0 = engine.get_state("domain-0")
        state_1 = engine.get_state("domain-1")

        assert state_0 is not None
        assert state_1 is not None
        assert state_0.phase == PrunePhase.HEALTHY, (
            f"domain-0 should be HEALTHY, got {state_0.phase}"
        )
        assert state_1.phase == PrunePhase.COLLAPSED, (
            f"domain-1 should be COLLAPSED, got {state_1.phase}"
        )

    # ------------------------------------------------------------------
    # Test 6: Recovery — node pulled back from WARNING to HEALTHY
    # ------------------------------------------------------------------

    def test_pruning_recovery(self, multi_miner_setup):
        """A node in WARNING that recovers its score returns to HEALTHY."""
        engine = PruningEngine(
            window_size=10,
            collapse_consecutive=8,
            warning_threshold=0.35,
            decay_threshold=0.20,
            min_traversals=1,
            nla_client=None,
        )
        engine.register_node("recover-node")

        # Push poor scores to move into WARNING
        for epoch in range(4):
            engine.push_scores(epoch, {
                "recover-node": EpochScore(
                    epoch=epoch, node_id="recover-node", score=0.25, traversal_count=2
                ),
            })
            engine.process_epoch(epoch)

        state_mid = engine.get_state("recover-node")
        assert state_mid is not None
        # Should be WARNING (score 0.25 is between 0.20 and 0.35)
        assert state_mid.phase in (PrunePhase.WARNING, PrunePhase.DECAYING), (
            f"Expected WARNING or DECAYING mid-run, got {state_mid.phase}"
        )

        # Now push strong scores to fill the window above warning_threshold mean
        for epoch in range(4, 12):
            engine.push_scores(epoch, {
                "recover-node": EpochScore(
                    epoch=epoch, node_id="recover-node", score=0.95, traversal_count=5
                ),
            })
            engine.process_epoch(epoch)

        state_final = engine.get_state("recover-node")
        assert state_final is not None
        assert state_final.phase == PrunePhase.HEALTHY, (
            f"Expected HEALTHY after recovery, got {state_final.phase}"
        )

    # ------------------------------------------------------------------
    # Test 7: Pruning collapse wires into GraphStore state
    # ------------------------------------------------------------------

    def test_pruning_collapse_updates_graph_store(self, multi_miner_setup):
        """CollapsePassage from PruningEngine updates GraphStore node state to Pruned."""
        setup = multi_miner_setup
        gs = GraphStore(db_path=str(setup["tmp_path"] / "collapse_test.db"))
        gs.add_node("weak-node", state="Live")
        gs.add_node("strong-node", state="Live")

        engine = PruningEngine(
            window_size=4,
            collapse_consecutive=3,
            warning_threshold=0.35,
            decay_threshold=0.20,
            min_traversals=1,
            nla_client=None,
        )
        engine.register_node("weak-node")
        engine.register_node("strong-node")

        for epoch in range(6):
            engine.push_scores(epoch, {
                "weak-node": EpochScore(
                    epoch=epoch, node_id="weak-node", score=0.02, traversal_count=3
                ),
                "strong-node": EpochScore(
                    epoch=epoch, node_id="strong-node", score=0.85, traversal_count=3
                ),
            })
            collapses = engine.process_epoch(epoch)
            for collapse in collapses:
                gs.set_node_state(collapse.node_id, "Pruned")

        weak = gs.get_node("weak-node")
        strong = gs.get_node("strong-node")

        assert weak is not None
        assert strong is not None
        assert weak.state == "Pruned", f"Expected Pruned, got {weak.state}"
        assert strong.state == "Live", f"Expected Live, got {strong.state}"

        # Pruned nodes should not appear in live_node_ids
        live_ids = gs.get_live_node_ids()
        assert "weak-node" not in live_ids
        assert "strong-node" in live_ids

    # ------------------------------------------------------------------
    # Test 8: MockSubtensor commitment round-trip
    # ------------------------------------------------------------------

    def test_mock_subtensor_commitment_isolation(self, multi_miner_setup):
        """MockSubtensor get_commitment returns None for UIDs with no commitment."""
        subtensor = multi_miner_setup["subtensor"]

        # UIDs 1-5 have commitments set in the fixture
        for uid in range(1, 6):
            cid = subtensor.get_commitment(netuid=0, uid=uid)
            assert cid is not None, f"UID {uid} should have a commitment"
            assert len(cid) == 64, f"CID should be 64-char sha256 hex, got {len(cid)}"

        # UID 99 has no commitment
        assert subtensor.get_commitment(netuid=0, uid=99) is None

        # Commitments are netuid-scoped
        assert subtensor.get_commitment(netuid=1, uid=1) is None

    # ------------------------------------------------------------------
    # Test 9: Edge decay reduces weight each epoch
    # ------------------------------------------------------------------

    def test_edge_decay_reduces_weight(self, multi_miner_setup):
        """decay_edges() reduces edge weight multiplicatively each call."""
        from subnet.config import EDGE_DECAY_FLOOR, EDGE_DECAY_RATE

        setup = multi_miner_setup
        gs = GraphStore(db_path=str(setup["tmp_path"] / "decay_test.db"))
        gs.upsert_edge("src", "dst", weight=10.0)

        initial_weight = gs.get_all_edges()[0].weight
        assert abs(initial_weight - 10.0) < 1e-6

        gs.decay_edges()
        edges_after = gs.get_all_edges()
        assert len(edges_after) > 0, "Edge should not be deleted after one decay from 10.0"
        decayed_weight = edges_after[0].weight
        expected = max(10.0 * EDGE_DECAY_RATE, EDGE_DECAY_FLOOR)
        assert abs(decayed_weight - expected) < 1e-5, (
            f"Expected {expected}, got {decayed_weight}"
        )

    # ------------------------------------------------------------------
    # Test 10: FakeEmbedder is deterministic
    # ------------------------------------------------------------------

    def test_fake_embedder_deterministic(self, multi_miner_setup):
        """FakeEmbedder produces identical 768-dim unit vectors for the same input."""
        embedder = FakeEmbedder(dim=768)

        v1 = embedder.embed_one("quantum mechanics")
        v2 = embedder.embed_one("quantum mechanics")
        v3 = embedder.embed_one("completely different text")

        assert v1 == v2, "Same input should produce same vector"
        assert v1 != v3, "Different inputs should produce different vectors"
        assert len(v1) == 768

        import math
        norm = math.sqrt(sum(x * x for x in v1))
        assert abs(norm - 1.0) < 1e-5, f"Expected unit vector, got norm={norm}"
