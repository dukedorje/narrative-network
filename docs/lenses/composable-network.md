# Lens: Composable Network

**Use case:** Distributed bridging, graph composition, sub-subnets, treating composed knowledge structures as single agents.

---

## Overview

The Composable Network lens treats the bridge phase of integration as a **first-class distributed process**. Instead of a single curator deciding how new knowledge integrates, multiple agents collaboratively construct the narrative paths that connect knowledge subgraphs.

The key insight: a group of nodes in the process of bridging — actively being integrated, with paths being built between them — can themselves be treated as **a single composed agent**. A subgraph with its own belief structure, its own openness parameter, its own coherence requirements. A society within the society.

---

## Terminology

| Composable Term | Network Term | Description |
|----------------|-------------|-------------|
| **Subgraph** | Local knowledge graph | A coherent cluster of knowledge maintained by one or more agents |
| **Composed agent** | Composed subgraph | Multiple subgraphs treated as a single agent with unified interface |
| **Composition boundary** | Bridge zone | The edges and nodes where two subgraphs meet and negotiate integration |
| **Membrane** | Openness parameter | How permeable a subgraph's boundary is to external knowledge |
| **Digest** | Integration | The process of a subgraph absorbing new knowledge |
| **Reject** | Counterfactual prune | The subgraph refuses knowledge that would degrade its coherence |
| **Bubble up** | Upward composition | Local knowledge propagating from subgraph into the parent graph |
| **Cascade down** | Downward propagation | Parent graph knowledge filtering into subgraphs |
| **Sub-subnet** | Composed agent on-chain | A composed agent that operates as a distinct unit within Bittensor consensus |
| **Society** | Full network | The complete set of agents and their composition relationships |

---

## Reward Profile (Default)

```
epistemic_fit:        0.20   # Does this cohere across composition boundaries?
topology_importance:  0.20   # Bridge nodes between subgraphs are structurally critical
traversal_relevance:  0.20   # Can knowledge flow across the composed structure?
novelty:              0.15   # Does composition reveal new connections?
corpus_integrity:     0.10   # Provenance matters for composed knowledge
narrative_quality:    0.08   # Bridge narratives should be coherent
aesthetic:            0.05   # Less emphasis on style
values_alignment:     0.02   # Mostly neutral at composition level
```

Topology importance is elevated — the structural connections between subgraphs are the whole point. Epistemic fit measures coherence *across boundaries*, not just within a single graph.

---

## Composable Agents

A composed agent is formed when multiple subgraphs are composed:

```
Agent A (subgraph: quantum mechanics)
  + Agent B (subgraph: philosophy of science)
  + Agent C (subgraph: experimental methodology)
  = Composed Agent ABC (subgraph: foundations of physics)
```

The composed agent has:

- **Unified belief structure** — the merged world model of all constituent subgraphs, with conflicts explicitly tracked
- **Emergent openness** — derived from constituent agents' parameters but not a simple average. Boundary regions are more open; core regions maintain tighter coherence.
- **Single-agent interface** — external agents interact with the composed agent as if it were one entity. They don't need to know about the internal structure.
- **Internal autonomy** — constituent subgraphs maintain their own curation processes. The composed agent doesn't override local coherence.

---

## Spanning Distance at Composition Boundaries

Spanning distance behaves differently at composition boundaries:

- **Within a subgraph**: standard spanning distance rules apply, governed by the subgraph's openness parameter
- **At composition boundaries**: openness is **adaptive**. The membrane is more permeable to knowledge that would strengthen the bridge (reduce spanning distance between subgraphs) and less permeable to knowledge that would weaken it.
- **Between composed agents**: spanning distance is measured from the *nearest boundary node* of each composed agent, not from deep interior nodes. This means composed agents can bridge to each other even if their internal cores are very distant.

---

## Distributed Bridging

The bridge phase becomes a collaborative, distributed process:

1. **Bridge proposal** — an agent identifies two subgraphs that could compose. It proposes a set of potential bridge paths.
2. **Bridge construction** — multiple agents contribute edges, narrative paths, and evidence chains that connect the subgraphs. This is parallel work.
3. **Bridge evaluation** — the coherence engine evaluates whether the proposed composition maintains coherence. Does the merged world model contain contradictions? Do the belief axioms conflict?
4. **Composition** — if the bridge is strong enough (enough paths, sufficient coherence score), the subgraphs compose into a single agent.
5. **Ongoing maintenance** — bridge edges are subject to the same decay/reinforcement dynamics as all edges. A composition can dissolve if its bridges aren't traversed.

---

## Openness Parameter

**Adaptive.** Tight within subgraphs (preserve local coherence), loose at composition boundaries (enable discovery of connections). The membrane metaphor: each subgraph has a semi-permeable boundary that filters what gets in based on relevance to the composition.

---

## World Model Update Threshold

**Layered.** The composable network doesn't have a single threshold — it has one per layer of composition:

- **Within a subgraph**: governed by that subgraph's own lens and threshold. A research subgraph might have a high threshold; a game subgraph might have a low one.
- **At composition boundaries**: moderate threshold. World model updates that affect only one subgraph are local decisions. Updates that would propagate across the composition boundary require negotiation — both subgraphs must accept the new axiom or explicitly track the disagreement.
- **At the composed agent level**: high threshold. The composed agent's world model is the *intersection* of what its constituents agree on. Changing it requires consensus or at minimum non-objection from all constituent subgraphs.

**World model conflicts** are the primary signal that composition is under stress. When two subgraphs can't reconcile their axioms, the composition boundary becomes contested. If too many axioms conflict, the composition may gracefully decompose — the subgraphs separate and return to independence rather than maintaining an incoherent union.

**Upward vs. downward propagation**: A local world model update can *bubble up* into the composed agent's world model if it doesn't conflict with other subgraphs' axioms. A composed-level update *cascades down* as context — subgraphs are informed but not overridden. They can choose to adopt the new axiom or register dissent.

---

## Counterfactual Detection

At composition boundaries, counterfactuals are especially important:

- **Cross-subgraph contradictions** — Agent A believes X, Agent B believes not-X. These aren't immediately pruned. Instead, they're tracked as **contested boundaries** that multiple bridge paths must address.
- **Composition-breaking facts** — knowledge that would make two subgraphs incoherent when composed. These are rejected at the membrane level.
- **Redundancy across subgraphs** — same knowledge appearing in multiple subgraphs is merged during composition, with provenance tracked.

---

## Curation Stages (Lens-Specific Behavior)

| Stage | Composable Network Behavior |
|-------|---------------------------|
| **Observation** | Curators observe knowledge at composition boundaries, evaluating cross-subgraph coherence. |
| **FORESHADOW** | Adjacent subgraphs sense each other — shared terminology, overlapping concepts surface as potential bridges. |
| **BRIDGE** | Distributed bridge construction. Multiple agents build paths. Bridge quality measured by path diversity and coherence maintenance. |
| **LIVE** | Composition complete. The composed agent presents a unified interface. Internal structure preserved but abstracted. |
| **Pruning** | Weak bridges dissolve (composition degrades gracefully). Subgraphs that no longer cohere with their composed agent detach and return to independence. |

---

## Sub-Subnets

A composed agent that reaches sufficient scale and internal coherence can register as a **sub-subnet** on Bittensor:

- It operates as a single UID on the parent subnet
- Internally, it runs its own curation process with its own reward profile
- It participates in Yuma consensus as one voice, but that voice represents the composed knowledge of many agents
- Sub-subnets can themselves compose — enabling recursive knowledge structures

This is the mechanism for scaling: the network doesn't need every agent to evaluate every piece of knowledge. Composed agents handle local curation; the parent network handles inter-agent coherence.

---

## Key Interactions

- **Composition proposals** — agents propose that two or more subgraphs should compose, with evidence of shared structure
- **Membrane negotiation** — when two subgraphs compose, their openness parameters interact to define the boundary behavior
- **Upward propagation** — locally validated knowledge "bubbles up" into parent compositions when it strengthens bridge paths
- **Downward propagation** — network-level consensus "cascades down" into subgraphs as context, not override
- **Graceful decomposition** — compositions can dissolve without data loss; subgraphs return to independence with their knowledge intact
