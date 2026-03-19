# Lens: Knowledge Network

**Use case:** Research, collaborative knowledge building, composing local knowledge graphs into shared understanding.

---

## Overview

The Knowledge Network lens tunes the Coherence Engine for **epistemic exploration** — agents research topics, build local knowledge graphs, and compose them upward into larger shared graphs. The emphasis is on coverage, accuracy, and productive disagreement rather than narrative beauty or entertainment.

An agent in this lens is a **researcher**. Researchers maintain local knowledge graphs that represent their current understanding. The network's job is to find where these understandings overlap, conflict, and complement each other — then compose them into a richer shared model.

---

## Reward Profile (Default)

```
epistemic_fit:        0.25   # Does this cohere with existing knowledge?
corpus_integrity:     0.20   # Can the agent prove its claims?
novelty:              0.20   # Does this expand what the network knows?
traversal_relevance:  0.15   # Does this connect well to adjacent knowledge?
topology_importance:  0.10   # Is this structurally important?
narrative_quality:    0.05   # Is the expression clear? (minimum bar, not emphasis)
aesthetic:            0.03   # Style matters less here
values_alignment:     0.02   # Mostly neutral
```

Corpus integrity and epistemic fit are weighted heavily — this lens cares about provable, coherent knowledge. Novelty is rewarded because the point is to *discover*, not to confirm.

---

## Openness Parameter

**High.** The Knowledge Network lens defaults to a wide openness radius. Researchers should be able to introduce distant, surprising knowledge. The cost is managed through the integration process — long-span knowledge takes longer to bridge but isn't rejected outright.

The coherence engine tolerates internal tension in this lens. Two contradictory claims can coexist in the graph as long as each is well-supported by its local corpus. The graph models the *disagreement* rather than forcing resolution.

---

## World Model Update Threshold

**High.** Paradigm shifts should be rare and well-earned. A single researcher's findings don't overturn established theory — it takes corroboration from multiple independent agents, survival of repeated challenges, and a critical mass of evidence that the existing axioms can't accommodate.

The threshold is also **asymmetric in favor of addition**: it's easier to extend the world model with new axioms (adding a new domain of knowledge) than to revoke existing ones (overturning established understanding). This mirrors how scientific consensus actually works — new fields emerge readily, but overturning existing consensus requires extraordinary evidence.

Counterfactuals accumulate as tracked disagreements. They sit in the graph as contested knowledge, visible to all researchers, until they either gather enough support to flip an axiom or fade as unsupported.

---

## Counterfactual Detection

In this lens, counterfactuals are handled carefully:

- **Contradictions are preserved**, not pruned — flagged as contested edges with evidence on both sides
- **Unsupported claims** (high confidence, low corpus integrity) are pruned aggressively
- **Redundant knowledge** (same claim, same evidence, different node) triggers merge proposals rather than pruning
- **Belief axiom updates** happen when a critical mass of evidence shifts — the graph's world model adjusts

---

## Composability

This is the primary lens for **composable knowledge graphs**:

- Individual researchers maintain local subgraphs
- Subgraphs can be **composed** — overlapping nodes are merged, conflicting edges are flagged, novel connections are surfaced
- A composed graph can be treated as a **single agent** with its own belief structure, openness parameter, and coherence requirements (see [composable-network.md](composable-network.md))
- Composition flows upward: local → team → domain → network-wide

---

## Curation Stages (Lens-Specific Behavior)

| Stage | Knowledge Network Behavior |
|-------|---------------------------|
| **Observation** | Researchers submit findings with corpus evidence. Curators evaluate epistemic fit and novelty, not narrative quality. |
| **FORESHADOW** | New knowledge appears as "pending research" — visible to adjacent researchers who may have corroborating or contradicting evidence. |
| **BRIDGE** | Bridge-building is collaborative: multiple researchers can contribute paths from existing knowledge to the new claim. Bridge quality measured by citation density, not narrative flow. |
| **LIVE** | Knowledge enters the shared graph. Its epistemic status is tracked (well-supported, contested, provisional). |
| **Pruning** | Targets unsupported or redundant claims. Contradictions are not pruned — they're marked as open questions. |

---

## Key Interactions

- **Merge proposals** — when two subgraphs contain overlapping knowledge, the coherence engine proposes merges with conflict resolution
- **Evidence chains** — traversal paths in this lens represent chains of evidence or reasoning, not narrative arcs
- **Confidence scoring** — nodes carry a confidence metric based on corpus depth, corroboration count, and challenge survival rate
- **Query-driven exploration** — researchers can target gaps in the graph, and the emission model rewards filling those gaps
