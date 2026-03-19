"""Tests for evolution.nla_settlement — NLA agreement building and settlement stubs.

All tests run without an NLA_API_KEY so no real HTTP calls are made.
Mock httpx tests verify the client correctly parses API responses and handles errors.
"""

from __future__ import annotations

import pytest
import respx
import httpx

from evolution.nla_settlement import NLAgreement, NLASettlementClient, SettlementResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> NLASettlementClient:
    """Client with no API key — operates in stub/no-op mode."""
    return NLASettlementClient(api_key="", endpoint="https://nla.test", chain="base")


@pytest.fixture
def keyed_client() -> NLASettlementClient:
    """Client with a fake API key — will make real (mocked) HTTP calls."""
    return NLASettlementClient(api_key="test-key-123", endpoint="https://nla.test", chain="base")


# ---------------------------------------------------------------------------
# Agreement text construction
# ---------------------------------------------------------------------------


class TestBuildProposalAgreement:
    def test_contains_proposer(self, client):
        a = client.build_proposal_agreement(
            proposal_id="abc123",
            proposer_hotkey="5GrwvaEF...",
            node_id="quantum-physics",
            proposal_type="ADD_NODE",
            bond_tao=2.5,
            voting_deadline_block=100000,
        )
        assert "5GrwvaEF..." in a.agreement_text
        assert "quantum-physics" in a.agreement_text
        assert "2.5000 TAO" in a.agreement_text
        assert "Block 100000" in a.agreement_text
        assert "Bittensor Knowledge Network subnet" in a.agreement_text

    def test_proposal_id_stored(self, client):
        a = client.build_proposal_agreement("p1", "hk", "n1", "ADD_NODE", 1.0, 7200)
        assert a.proposal_id == "p1"
        assert a.status == "draft"
        assert a.escrow_uid == ""

    def test_metadata_populated(self, client):
        a = client.build_proposal_agreement("p1", "hk", "n1", "ADD_NODE", 3.0, 9000)
        assert a.metadata["bond_tao"] == 3.0
        assert a.metadata["node_id"] == "n1"
        assert a.metadata["voting_deadline_block"] == 9000


class TestBuildIntegrationAgreement:
    def test_contains_live_block(self, client):
        a = client.build_integration_agreement(
            proposal_id="p2",
            node_id="astro-01",
            proposer_hotkey="5DAAnrj7",
            bond_tao=1.0,
            live_block=55000,
        )
        assert "astro-01" in a.agreement_text
        assert "55000" in a.agreement_text
        assert "returned" in a.agreement_text.lower()
        assert a.proposal_id == "p2"

    def test_integration_agreement_terms(self, client):
        a = client.build_integration_agreement("p3", "node-x", "hk2", 1.5, 60000)
        assert "RAMP" in a.agreement_text or "score" in a.agreement_text.lower()


class TestBuildCollapseAgreement:
    def test_contains_reason(self, client):
        a = client.build_collapse_agreement(
            node_id="old-node",
            proposer_hotkey="5HGjWAe...",
            bond_tao=0.5,
            epoch=42,
            reason="3 consecutive epochs below decay threshold 0.20",
        )
        assert "old-node" in a.agreement_text
        assert "42" in a.agreement_text
        assert "3 consecutive" in a.agreement_text
        assert "burned" in a.agreement_text.lower()

    def test_collapse_proposal_id_format(self, client):
        a = client.build_collapse_agreement("n1", "hk", 0.5, 10, "reason")
        assert a.proposal_id == "collapse:n1:10"


# ---------------------------------------------------------------------------
# Stub mode (no API key)
# ---------------------------------------------------------------------------


class TestStubMode:
    async def test_register_stub_returns_draft(self, client):
        agreement = NLAgreement(
            agreement_text="test agreement",
            proposal_id="stub-p1",
        )
        result = await client.register(agreement)
        assert result.status == "draft"
        assert result.escrow_uid == ""

    async def test_settle_return_stub_succeeds(self, client):
        agreement = NLAgreement(
            agreement_text="test",
            proposal_id="stub-p1",
            escrow_uid="",
        )
        result = await client.settle(
            agreement=agreement,
            action="return",
            proposal_id="stub-p1",
            bond_tao=2.0,
            proposer_hotkey="5abc...",
        )
        assert result.success is True
        assert result.action == "bond_returned"
        assert result.proposal_id == "stub-p1"

    async def test_settle_burn_stub_succeeds(self, client):
        agreement = NLAgreement(
            agreement_text="test",
            proposal_id="stub-p2",
            escrow_uid="",
        )
        result = await client.settle(
            agreement=agreement,
            action="burn",
            proposal_id="stub-p2",
            bond_tao=1.0,
            proposer_hotkey="5abc...",
        )
        assert result.success is True
        assert result.action == "bond_burned"

    async def test_keyed_client_with_empty_escrow_uid_uses_stub(self, keyed_client):
        """Even with an API key, missing escrow_uid falls back to stub settle."""
        agreement = NLAgreement(
            agreement_text="test",
            proposal_id="p-nouid",
            escrow_uid="",
        )
        result = await keyed_client.settle(
            agreement=agreement,
            action="return",
            proposal_id="p-nouid",
            bond_tao=1.0,
            proposer_hotkey="hk",
        )
        assert result.success is True


# ---------------------------------------------------------------------------
# Live API mock (respx)
# ---------------------------------------------------------------------------


class TestMockedAPI:
    @respx.mock
    async def test_register_success(self, keyed_client):
        respx.post("https://nla.test/v1/agreements").mock(
            return_value=httpx.Response(200, json={"escrow_uid": "uid-aabbcc"})
        )
        agreement = NLAgreement(agreement_text="text", proposal_id="p-live")
        result = await keyed_client.register(agreement)
        assert result.status == "registered"
        assert result.escrow_uid == "uid-aabbcc"

    @respx.mock
    async def test_register_http_error_falls_back_to_draft(self, keyed_client):
        respx.post("https://nla.test/v1/agreements").mock(
            return_value=httpx.Response(503, json={"error": "service unavailable"})
        )
        agreement = NLAgreement(agreement_text="text", proposal_id="p-err")
        result = await keyed_client.register(agreement)
        assert result.status == "draft"

    @respx.mock
    async def test_settle_return_success(self, keyed_client):
        respx.post("https://nla.test/v1/agreements/uid-aabbcc/settle").mock(
            return_value=httpx.Response(
                200,
                json={"fulfillment_uid": "fuid-xyz", "tx_hash": "0xdeadbeef"},
            )
        )
        agreement = NLAgreement(
            agreement_text="text", proposal_id="p-settle", escrow_uid="uid-aabbcc"
        )
        result = await keyed_client.settle(
            agreement=agreement,
            action="return",
            proposal_id="p-settle",
            bond_tao=2.0,
            proposer_hotkey="5abc...",
        )
        assert result.success is True
        assert result.tx_hash == "0xdeadbeef"
        assert result.action == "bond_returned"
        assert agreement.status == "returned"

    @respx.mock
    async def test_settle_burn_updates_status(self, keyed_client):
        respx.post("https://nla.test/v1/agreements/uid-burn/settle").mock(
            return_value=httpx.Response(200, json={"fulfillment_uid": "fuid-burn", "tx_hash": "0x1"})
        )
        agreement = NLAgreement(
            agreement_text="text", proposal_id="p-burn", escrow_uid="uid-burn"
        )
        await keyed_client.settle(
            agreement=agreement,
            action="burn",
            proposal_id="p-burn",
            bond_tao=1.0,
            proposer_hotkey="hk",
        )
        assert agreement.status == "burned"

    @respx.mock
    async def test_settle_network_error_returns_failure(self, keyed_client):
        respx.post("https://nla.test/v1/agreements/uid-err/settle").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        agreement = NLAgreement(
            agreement_text="text", proposal_id="p-net", escrow_uid="uid-err"
        )
        result = await keyed_client.settle(
            agreement=agreement,
            action="return",
            proposal_id="p-net",
            bond_tao=1.0,
            proposer_hotkey="hk",
        )
        assert result.success is False
        assert result.error != ""
