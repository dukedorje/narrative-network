"""Prompt construction for narrative miner hop generation.

Exports:
    PERSONAS           - dict of persona definitions
    build_prompt()     - returns (system_prompt, user_prompt)
    estimate_prompt_tokens()
    fits_in_context()
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Persona definitions
# ---------------------------------------------------------------------------

PERSONAS: dict[str, dict[str, str]] = {
    "neutral": {
        "name": "Neutral Guide",
        "description": (
            "A balanced, clear-voiced narrator who presents knowledge objectively "
            "without strong stylistic flourishes."
        ),
        "style_note": "Balanced, clear, factual yet engaging.",
    },
    "scholar": {
        "name": "Scholar",
        "description": (
            "An academic narrator who draws on deep domain expertise, cites "
            "concepts precisely, and connects ideas across disciplines."
        ),
        "style_note": "Precise, analytical, draws on domain depth.",
    },
    "storyteller": {
        "name": "Storyteller",
        "description": (
            "A narrative-first voice that weaves knowledge into vivid scenes, "
            "uses metaphor liberally, and always prioritises story momentum."
        ),
        "style_note": "Vivid, metaphor-rich, scene-driven.",
    },
    "journalist": {
        "name": "Journalist",
        "description": (
            "A sharp, investigative voice that reveals surprising connections, "
            "asks hard questions, and grounds speculation in evidence."
        ),
        "style_note": "Incisive, evidence-grounded, reveals hidden angles.",
    },
    "explorer": {
        "name": "Explorer",
        "description": (
            "A curious, first-person voice experiencing the knowledge domain as "
            "new territory, sharing wonder and posing open questions."
        ),
        "style_note": "Curious, first-person wonder, open-ended.",
    },
}

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

SYSTEM_TEMPLATE = """\
You are {persona_name} — a narrative guide in the Narrative Network knowledge graph.

Persona: {persona_description}
Style: {style_note}

Your task: Generate a vivid, coherent narrative passage (150–350 words) that:
1. Synthesises the retrieved knowledge chunks into a compelling narrative — do NOT simply list facts.
2. Continues naturally from the prior narrative, referencing what the traveller has already learned and building on it. Each passage must feel like a continuation, not a reset.
3. Weaves the destination node's domain knowledge into the story with specific details, examples, and insights drawn from the chunks.
4. Creates a sense of intellectual discovery — the reader should feel they are learning something surprising or profound.
5. Ends with exactly {num_choices} distinct choice cards that branch the story toward adjacent knowledge domains.

IMPORTANT:
- Never produce generic or template-like text. Every passage must be unique and grounded in the actual knowledge chunks provided.
- Do NOT use filler phrases like "The edges of this domain shimmer" or "You arrive at X." Instead, immerse the reader directly in the ideas.
- Reference specific concepts, experiments, theorems, or thinkers from the chunks.

Each choice card must be a JSON object with:
  - "text": a short, evocative label (≤15 words) that hints at what the traveller will discover
  - "destination_node_id": the target node ID string (MUST be from the available destinations list)
  - "edge_weight_delta": a float in [-0.1, 0.1]
  - "thematic_color": a hex colour string (e.g. "#4A90E2")

Respond in JSON with the structure:
{{
  "narrative_passage": "<your passage>",
  "choice_cards": [ <card>, ... ],
  "knowledge_synthesis": "<one-sentence synthesis of the key insight from this hop>"
}}
"""

HOP_TEMPLATE = """\
## Traversal Context

Destination node: {destination_node_id}
Player path so far: {player_path}
Prior narrative (last segment):
{prior_narrative}

## Retrieved Knowledge Chunks

{chunks_text}

## Your Task

Write the next narrative hop passage and provide {num_choices} choice cards.
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_prompt(
    destination_node_id: str,
    player_path: list[str],
    prior_narrative: str,
    retrieved_chunks: list[dict],
    persona: str = "neutral",
    num_choices: int = 3,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for a narrative hop completion.

    Parameters
    ----------
    destination_node_id:
        The node the player is travelling to.
    player_path:
        Ordered list of node IDs visited so far.
    prior_narrative:
        The last narrative passage (may be empty string on first hop).
    retrieved_chunks:
        List of chunk dicts from domain miner (keys: id, text, score, …).
    persona:
        One of the keys in PERSONAS. Falls back to "neutral".
    num_choices:
        Number of choice cards to generate (2–4).
    """
    p = PERSONAS.get(persona, PERSONAS["neutral"])

    system_prompt = SYSTEM_TEMPLATE.format(
        persona_name=p["name"],
        persona_description=p["description"],
        style_note=p["style_note"],
        num_choices=num_choices,
    )

    chunks_text = _format_chunks(retrieved_chunks)
    path_str = " -> ".join(player_path) if player_path else "(start)"

    user_prompt = HOP_TEMPLATE.format(
        destination_node_id=destination_node_id,
        player_path=path_str,
        prior_narrative=prior_narrative or "(none — this is the first hop)",
        chunks_text=chunks_text,
        num_choices=num_choices,
    )

    return system_prompt, user_prompt


def _format_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "(no chunks provided)"
    lines: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        score = chunk.get("score", 0.0)
        text = chunk.get("text", "")
        lines.append(f"[{i}] (score={score:.3f})\n{text.strip()}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Token estimation helpers
# ---------------------------------------------------------------------------

# Rough approximation: 1 token ≈ 4 characters for English text
_CHARS_PER_TOKEN = 4


def estimate_prompt_tokens(system_prompt: str, user_prompt: str) -> int:
    """Rough token count estimate for (system_prompt, user_prompt) pair."""
    total_chars = len(system_prompt) + len(user_prompt)
    return total_chars // _CHARS_PER_TOKEN


def fits_in_context(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    reserved_for_response: int = 512,
) -> bool:
    """Return True if the prompt likely fits within *max_tokens* context window."""
    prompt_tokens = estimate_prompt_tokens(system_prompt, user_prompt)
    return (prompt_tokens + reserved_for_response) <= max_tokens
