"""Unit tests for domain.unified_miner.Miner._forward_nh() with mocked _generate."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import domain.unified_miner as _unified_miner_mod
from domain.unified_miner import Miner
from subnet.protocol_local import NarrativeHop

# ---------------------------------------------------------------------------
# Minimal stand-in — only attributes _forward_nh needs
# ---------------------------------------------------------------------------


class MinimalMiner:
    """Minimal stand-in with just the attributes _forward_nh needs."""

    def __init__(self, uid=1, node_id="test-node", persona="neutral"):
        self.uid = uid
        self.node_id = node_id
        self.persona = persona
        self.session_store = MagicMock()
        self.session_store.get_field = AsyncMock(return_value=[])
        self.session_store.update_field = AsyncMock()
        # _generate is patched per-test via AsyncMock on the instance
        self._generate = None
        self._update_session = AsyncMock()
        # Unbrowse stub — no API key means no-op
        from orchestrator.unbrowse import UnbrowseClient
        self._unbrowse = UnbrowseClient(api_key="")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_miner():
    miner = MinimalMiner(uid=1, node_id="test-node", persona="neutral")
    # Patch module-level guard so _forward_nh doesn't short-circuit on missing key
    with patch.object(_unified_miner_mod, "_OPENROUTER_API_KEY", "sk-test"):
        yield miner


@pytest.fixture
def good_llm_result():
    """Valid parsed dict that _generate would return."""
    return {
        "narrative_passage": "You step into the quantum realm " + " ".join(["word"] * 197),
        "knowledge_synthesis": "Quantum mechanics reveals...",
        "choice_cards": [
            {"text": "Explore entanglement", "destination_node_id": "node-2"},
            {"text": "Study wave functions", "destination_node_id": "node-3"},
        ],
    }


def _make_synapse(**kwargs):
    defaults = dict(
        destination_node_id="node-2",
        player_path=["node-1"],
        session_id="test-session-001",
        retrieved_chunks=[],
    )
    defaults.update(kwargs)
    return NarrativeHop(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_forward_returns_passage(minimal_miner, good_llm_result):
    """Mocked LLM returns a narrative passage in the synapse."""
    minimal_miner._generate = AsyncMock(return_value=good_llm_result)

    synapse = _make_synapse()
    result = await Miner._forward_nh(minimal_miner, synapse)

    assert result.narrative_passage is not None
    assert len(result.narrative_passage) > 0
    assert result.narrative_passage != "(generation failed)"


async def test_forward_returns_choice_cards(minimal_miner, good_llm_result):
    """Choice cards are parsed correctly from LLM result dict."""
    minimal_miner._generate = AsyncMock(return_value=good_llm_result)

    synapse = _make_synapse()
    result = await Miner._forward_nh(minimal_miner, synapse)

    assert result.choice_cards is not None
    assert len(result.choice_cards) == 2
    assert result.choice_cards[0].text == "Explore entanglement"
    assert result.choice_cards[0].destination_node_id == "node-2"
    assert result.choice_cards[1].text == "Study wave functions"
    assert result.choice_cards[1].destination_node_id == "node-3"


async def test_forward_sets_agent_uid(minimal_miner, good_llm_result):
    """Response synapse carries the correct agent_uid."""
    minimal_miner._generate = AsyncMock(return_value=good_llm_result)

    synapse = _make_synapse()
    result = await Miner._forward_nh(minimal_miner, synapse)

    assert result.agent_uid == 1


async def test_forward_handles_generation_failure(minimal_miner):
    """When _generate returns None, narrative_passage is '(generation failed)'."""
    minimal_miner._generate = AsyncMock(return_value=None)

    synapse = _make_synapse()
    result = await Miner._forward_nh(minimal_miner, synapse)

    assert result.narrative_passage == "(generation failed)"
    assert result.choice_cards == []
    assert result.agent_uid == 1


async def test_forward_handles_malformed_json(minimal_miner):
    """_generate returning None (as it would on JSONDecodeError) produces '(generation failed)'."""
    # _generate already handles JSON errors internally and returns None
    minimal_miner._generate = AsyncMock(return_value=None)

    synapse = _make_synapse()
    result = await Miner._forward_nh(minimal_miner, synapse)

    assert result.narrative_passage == "(generation failed)"
    assert result.choice_cards == []


async def test_forward_handles_malformed_choice_cards(minimal_miner):
    """Invalid card entries are skipped; valid ones are kept."""
    result_with_bad_cards = {
        "narrative_passage": "A valid passage about the quantum realm and its mysteries.",
        "knowledge_synthesis": "Some synthesis.",
        "choice_cards": [
            {"text": "Valid card", "destination_node_id": "node-5"},
            "this is not a dict",   # skipped
            None,                   # skipped
            42,                     # skipped
        ],
    }
    minimal_miner._generate = AsyncMock(return_value=result_with_bad_cards)

    synapse = _make_synapse()
    result = await Miner._forward_nh(minimal_miner, synapse)

    assert result.choice_cards is not None
    assert len(result.choice_cards) == 1
    assert result.choice_cards[0].text == "Valid card"
    assert result.choice_cards[0].destination_node_id == "node-5"
