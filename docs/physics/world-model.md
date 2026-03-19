# World Model

The **world model** is the set of axioms — rules, assumptions, and established truths — that the knowledge graph treats as foundational. It is not the graph itself, but the framework that determines what *can be true* within the graph. New knowledge is evaluated against the world model, not just against neighboring nodes.

---

## Axioms

An axiom is a foundational belief that the graph treats as true. Axioms are not nodes — they're the rules that nodes are evaluated against. Examples:

- "Quantum mechanics and general relativity are both valid but incompatible at certain scales"
- "The capital city of the realm is Aldenmere"
- "Energy is conserved"
- "This faction and that faction are at war"

Axioms can be explicit (stated and tracked) or emergent (implied by the topology and content of the graph). The coherence engine enforces axioms by scoring epistemic fit — knowledge that contradicts an axiom scores poorly on that axis.

---

## Mutability

The world model is **mutable**, but changing it is a significant event — not routine curation. When a world model update occurs, it doesn't just add knowledge; it **recontextualizes existing knowledge**. Downstream nodes, edges, and scoring relationships may shift in meaning even if their data doesn't change.

### World Events

A **world event** is an occurrence that updates the world model itself. World events are distinguished from normal knowledge additions by their propagation effects:

**When an axiom changes:**
- Existing knowledge that depended on the old axiom is re-evaluated
- Some nodes may become counterfactual (they were coherent under the old model but aren't under the new one)
- New integration paths open up that were previously too distant
- The reward profile may shift to reflect new priorities

**Examples:**
- **Game**: A dragon destroys the capital city. "The capital exists" is no longer an axiom. Every agent's knowledge graph is affected. Trade routes, political structures, quest lines all recontextualize.
- **Knowledge Network**: A paradigm shift. Relativity doesn't just add nodes about spacetime — it changes the axioms that Newtonian mechanics was built on. Existing nodes aren't deleted but their epistemic status changes.
- **Composable Network**: Each subgraph carries its own world model. Composition requires **world model negotiation** — can these axiom sets coexist? If not, which yields? A composed agent's world model is the intersection of what its constituents agree on, plus explicitly tracked disagreements.

---

## Update Threshold

The **world model update threshold** is a lens parameter — one of the most consequential dials in the system. It controls how much evidence, consensus, or narrative force is required before an axiom can change:

- **High threshold**: Paradigm shifts are rare. Requires overwhelming, well-corroborated evidence from multiple agents. The world model is conservative and stable. Counterfactuals accumulate as tracked disagreements for a long time before they can flip an axiom.
- **Moderate threshold**: World model updates require negotiation. Updates are possible but require substantial justification.
- **Low threshold**: The world is alive and changeable. Major events can update axioms. This makes the world feel dynamic but requires strong coherence enforcement downstream to prevent incoherence through rapid successive updates.

The threshold can also be **asymmetric**: it might be easy to *add* new axioms (the world grows) but hard to *revoke* existing ones (established truths resist overturning). Or vice versa — a world where nothing is sacred and everything can be questioned.

---

## Per-Agent World Models

Individual agents may maintain their own world models that diverge from the network consensus:

- An agent's **local world model** may lag behind or run ahead of the network's
- A zealot clings to old axioms long after the world has moved on
- A prophet accepts new truths before anyone else
- This creates tension between agents who live in different versions of reality

The network's consensus world model is what Yuma consensus produces. Individual agents' world models are their own epistemic states.

---

## Relationship to Other Physics

- **Counterfactual Detection**: The world model is the ground truth against which counterfactuals are measured. See [counterfactual-detection.md](counterfactual-detection.md).
- **Observation & Integration**: The world model determines what spanning distances are "close" or "far" — it sets the semantic landscape that distance is measured across. See [observation-and-integration.md](observation-and-integration.md).
- **Hole Detection**: The world model implies what *should* exist — holes are gaps between what the axioms predict and what the graph contains. See [hole-detection.md](hole-detection.md).
