# Counterfactual Detection

Grooming the knowledge graph — finding contradictions, resolving or tracking them, and updating axioms when the evidence demands it.

---

## What Is a Counterfactual?

A **counterfactual** is knowledge that contradicts the current world model. Not "low quality" or "unpopular" — specifically *incoherent with what the graph holds as true*.

Counterfactual detection is the coherence engine's immune system. It keeps the graph from absorbing facts that would degrade the quality of its world model — unless those facts turn out to be true, in which case the world model updates.

---

## Detection

Counterfactuals are detected through multiple signals:

### Direct Contradiction
A new claim explicitly negates an existing axiom or well-established node.
- "The capital was never destroyed" when the world model says it was
- "Energy is not conserved" when conservation is an axiom

### Inference Contradiction
A new claim doesn't directly contradict anything, but its logical consequences do.
- A node claims X, and X combined with existing node Y implies Z, but Z contradicts axiom W
- Requires reasoning over the graph's structure, not just pairwise comparison

### Drift Contradiction
A node's content has gradually shifted away from its declared domain — it's no longer what it claims to be.
- Already implemented as drift detection (cosine distance from centroid > `DRIFT_MAX_COSINE_DISTANCE`)
- Generalized: any agent whose behavior has drifted from its world model

### Redundancy
Not a contradiction per se, but the same claim from the same evidence appearing in multiple places. Creates false confidence (the graph thinks it has three independent sources, but it's really one).
- Detected by high embedding similarity between nodes with overlapping corpus

---

## Grooming Process

Once a counterfactual is detected, the grooming process determines what to do with it. This is **not** automatic deletion — the response depends on the lens and the nature of the contradiction.

### Stage 1: Flag

The counterfactual is identified and tagged with:
- What it contradicts (which axiom, which node, which inference chain)
- How strong the contradiction is (direct vs. inferred, single source vs. multiple)
- How well-supported the counterfactual itself is (corpus integrity, traversal history, corroboration)

### Stage 2: Evaluate

The coherence engine evaluates whether this is a genuine contradiction or a nuance:

- **Genuine contradiction**: X and not-X cannot both be true under the current world model
- **Perspective difference**: X is true in one context, not-X in another — the world model needs refinement, not a flip
- **Scope conflict**: X is true at one scale/time/domain, not-X at another — the axioms need to be scoped more precisely
- **Noise**: The contradiction is an artifact of imprecise language or embedding similarity — not a real conflict

### Stage 3: Resolve

Resolution strategies, ordered from least to most disruptive:

| Strategy | When to use | Effect |
|----------|------------|--------|
| **Dismiss** | Noise or artifact | Remove the flag, no action |
| **Scope** | Scope conflict | Refine the axiom to be more precise ("X is true *within domain D*") |
| **Track** | Genuine contradiction, insufficient evidence to resolve | Mark as contested — both claims coexist with a tracked disagreement |
| **Prune** | Counterfactual is weakly supported, existing axiom is strong | Remove the contradicting node, strengthen the axiom |
| **Update** | Counterfactual is well-supported, existing axiom is weak | World model update — the axiom flips. Former truth becomes the new counterfactual. This is a **world event**. |

### Stage 4: Propagate

After resolution, propagate the effects:

- **If dismissed or scoped**: Minimal propagation. Nearby agents are notified of the refinement.
- **If tracked**: The disagreement is visible to all agents traversing the contested region. Probes may be dispatched to seek resolution.
- **If pruned**: The pruned node's edges decay. Active sessions are rerouted. Dependent knowledge is re-evaluated.
- **If updated (world event)**: Full propagation. All agents re-evaluate knowledge that depended on the old axiom. See [world-model.md](world-model.md) for world event mechanics.

---

## Counterfactual Accumulation

Before an axiom flips, counterfactuals **accumulate**. The graph doesn't flip on the first contradiction — it tracks disagreements and lets evidence build.

The **accumulation threshold** determines how many independent counterfactual signals are needed before the coherence engine considers an axiom update:

- Multiple independent agents reporting the same contradiction
- Contradicting evidence surviving corpus integrity challenges
- Traversals through the contested region producing consistently better scores when the counterfactual is assumed true

When the accumulation threshold is reached, the coherence engine triggers a world model update evaluation. This evaluation may still result in "track" (keep accumulating) if the evidence isn't decisive.

---

## Across Lenses

Each lens handles counterfactuals differently — the physics provides the process, the lens provides the policy:

| Aspect | Knowledge Network | Game | Composable Network |
|--------|-------------------|------|-------------------|
| **Detection emphasis** | Inference contradictions, redundancy | Direct contradictions (plot holes) | Cross-boundary conflicts |
| **Preferred resolution** | Track (preserve disagreement) | Prune or Update (resolve for narrative coherence) | Scope (refine axioms at boundaries) |
| **Accumulation threshold** | High (scientific rigor) | Low to moderate (narrative pacing) | Layered (per-subgraph, per-boundary, per-composition) |
| **Propagation speed** | Slow (let evidence build) | Fast (world events should feel immediate) | Variable (local fast, composed slow) |

---

## Relationship to Other Physics

- **World Model**: The ground truth that counterfactuals are measured against. Updates to the world model are the most consequential outcome of counterfactual resolution. See [world-model.md](world-model.md).
- **Hole Detection**: Counterfactual pruning can *create* holes — removing a node may disconnect part of the graph. The hole detection process should run after significant pruning. See [hole-detection.md](hole-detection.md).
- **Internal Economics**: Counterfactual detection costs energy. Aggressive grooming requires compute budget. See [internal-economics.md](internal-economics.md).
- **Observation & Integration**: New knowledge arriving through integration is the primary source of potential counterfactuals. See [observation-and-integration.md](observation-and-integration.md).
