# Lens: Game

**Use case:** Narrative generative experiences — interactive fiction, emergent worldbuilding, NPC simulation, collaborative storytelling.

---

## Overview

The Game lens tunes the Coherence Engine for **narrative emergence**. Agents are modeled as autonomous entities within a living story world. Each agent maintains a local knowledge graph representing what it knows, believes, and has experienced. Narrative hops become **actions in the story** — things that happen, change the world, and update each agent's understanding.

The network doesn't tell a predetermined story. It simulates a world populated by agents with independent knowledge and perspectives, and stories emerge from their interactions.

---

## Terminology

In this lens, specific terms map to the primary network concepts:

| Game Term | Network Term | Description |
|-----------|-------------|-------------|
| **Player** | Traversing agent | A human-controlled agent navigating the story world |
| **NPC** | Autonomous agent | An AI-driven agent with its own knowledge graph and motivations |
| **World** | Knowledge graph | The shared reality all agents inhabit |
| **Lore** | Corpus | The established facts, history, and rules of the world |
| **Scene** | Hop | A discrete narrative moment — something happens, the world changes |
| **Action** | Traversal | An agent's choice that moves the story forward |
| **Memory** | Local knowledge graph | What an individual agent knows and has experienced |
| **Worldbuilder** | Curator | The agent that shapes what's real, what's possible, what matters |
| **Canon** | World model | The set of facts the world considers true |
| **Plot hole** | Counterfactual | An inconsistency that breaks narrative coherence |
| **Backstory** | FORESHADOW phase | Hints of new elements before they fully enter the world |
| **Introduction** | BRIDGE phase | New elements woven into the existing narrative fabric |
| **Retcon** | Belief axiom update | When established canon changes because new evidence demands it |

---

## Reward Profile (Default)

```
narrative_quality:    0.25   # Is the scene compelling, well-paced, evocative?
aesthetic:            0.20   # Does this enrich the world's texture and tone?
epistemic_fit:        0.20   # Is this consistent with established canon?
traversal_relevance:  0.15   # Does this scene connect meaningfully to what came before?
novelty:              0.10   # Does this introduce surprising developments?
values_alignment:     0.05   # Does this fit the world's moral/thematic framework?
topology_importance:  0.03   # Structural importance (less critical in game context)
corpus_integrity:     0.02   # Minimum bar — agents should know their own lore
```

Narrative quality and aesthetic are dominant. This lens optimizes for *experience* — the story should be compelling, consistent, and surprising.

---

## Openness Parameter

**Moderate.** New lore should feel connected to existing lore. Wild, ungrounded additions break immersion. But the world should be capable of genuine surprise — new factions, unexpected revelations, emergent plot twists.

The sweet spot: new elements that feel inevitable in retrospect but weren't predictable in advance.

---

## Agents as NPCs

Each NPC is an agent with:

- A **local knowledge graph** (memory) — what this agent knows, has witnessed, believes
- A **persona embedding** — personality, speech patterns, values, motivations
- An **openness parameter** — how readily this agent accepts new information (a paranoid spy vs. a curious scholar)
- An **action vocabulary** — what kinds of narrative hops this agent can generate

NPCs **think from their knowledge graphs**. When a player interacts with an NPC, the NPC's responses are generated from its local knowledge — not from omniscient world state. An NPC who wasn't present for an event doesn't know about it. An NPC who was lied to believes the lie.

This creates emergent dramatic irony: the player may know things that NPCs don't, and vice versa.

---

## World Model Update Threshold

**Low to moderate.** The world should feel alive — things happen that change reality. A dragon destroys a city, a secret society is revealed, a natural law turns out to work differently than everyone thought. These are **world events** and they're part of what makes the game compelling.

But not *too* low. If canon changes every scene, nothing feels real. The threshold should be tuned so that world events feel like climactic moments — earned through narrative buildup, not random. The FORESHADOW phase becomes critical here: world events should be hinted at before they land.

**Asymmetry**: easy to *add* canon (the world grows, new factions appear, new lands are discovered) but moderately hard to *revoke* canon (you can't just un-destroy a city without a strong narrative justification). Retcons are possible but should feel intentional — a revelation that recontextualizes, not an erasure.

**Per-agent world models**: Individual NPCs may have *local* world model thresholds that differ from the global one. A zealot clings to old axioms long after the world has moved on. A prophet accepts new truths before anyone else. This creates narrative tension between agents who live in different versions of reality.

---

## Counterfactual Detection (Plot Hole Repair)

In this lens, counterfactuals are **plot holes** — inconsistencies that break narrative coherence:

- An NPC references an event that hasn't happened yet (unless foreshadowing)
- A scene contradicts established canon without justification
- Two agents' memories of the same event differ in incompatible ways (this one is interesting — it can be preserved as unreliable narration or flagged for resolution)

The coherence engine either **repairs** the plot hole (retcon, reinterpretation) or **leans into it** (unreliable narrators, hidden information, conspiracy). The choice depends on the world's values alignment settings.

---

## Curation Stages (Lens-Specific Behavior)

| Stage | Game Behavior |
|-------|--------------|
| **Observation** | Scenes are generated, worldbuilders evaluate narrative quality and canon consistency. |
| **FORESHADOW** | New world elements appear as rumors, omens, distant events. Players and NPCs may notice hints. ("Backstory") |
| **BRIDGE** | New elements are woven into the narrative through introductory scenes. An NPC arrives, a location is discovered, a faction makes contact. ("Introduction") |
| **LIVE** | The element is part of canon. It can be referenced, interacted with, built upon. |
| **Pruning** | Plot holes and orphaned lore are removed. But pruning is narrative — a forgotten god, a burned library, a redacted history. Collapse events become story moments. |

---

## Key Interactions

- **Scene generation** — each hop produces a narrative scene, not a knowledge summary
- **NPC autonomy** — NPCs act from their own knowledge graphs, creating emergent behavior
- **World consistency** — the coherence engine maintains canon across all agents' local knowledge
- **Player agency** — player actions genuinely change the world model, with consequences that propagate through NPC knowledge graphs
- **Emergent lore** — the world's history is written by the accumulation of scenes, not by a designer
