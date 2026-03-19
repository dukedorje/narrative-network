# Physics — Universal Rules of the Network

The physics are the invariant rules that govern how the knowledge graph behaves. Every lens inherits these rules and configures parameters over them, but cannot violate them.

Lenses tune the physics. They don't replace them.

---

## The Coherence Engine

The Coherence Engine is the meta-process that orchestrates all physics. It is the system by which curators (validators, in Bittensor protocol terms) shape the knowledge graph. It operates through six processes:

1. **Observation** — Selection of phenomena into the graph's reality
2. **Integration** — Absorption of new knowledge via bridge-building
3. **Counterfactual Detection** — Grooming the graph for contradictions and incoherence
4. **Hole Detection** — Finding what's missing
5. **Reward Shaping** — Mutable reward profiles that steer curation
6. **Supervision** — Agent lifecycle, compute allocation, scheduling

Each process has its own document below. Together they define how the graph lives, grows, and maintains itself.

---

## Processes

| Process | Doc | What it does |
|---------|-----|-------------|
| **World Model** | [world-model.md](world-model.md) | The axioms that determine what can be true. Ground truth for coherence. |
| **Observation & Integration** | [observation-and-integration.md](observation-and-integration.md) | How phenomena are selected into reality and new knowledge is absorbed. Spanning distance, openness, bridge-building. |
| **Counterfactual Detection** | [counterfactual-detection.md](counterfactual-detection.md) | Grooming the graph — finding contradictions, resolving or tracking them, updating axioms when the evidence demands it. |
| **Hole Detection & Probing** | [hole-detection.md](hole-detection.md) | Finding what's missing. Probe abstraction for investigating gaps. |
| **Internal Economics** | [internal-economics.md](internal-economics.md) | Energy model, compute budgeting, priority allocation. |
| **Supervision** | [supervision.md](supervision.md) | Erlang-style agent lifecycle, scheduling, mailbox model. |

---

## Agents

Every participant in the network is an **agent**: curators, miners, traversing entities, composed subgraphs. Agents have:

- A **world model** (the axioms they treat as foundational — what they believe is true about reality)
- A **belief structure** (their current knowledge graph state, built on top of their world model)
- An **openness parameter** (max spanning distance for integration)
- A **coherence requirement** (how many bridge paths needed before something becomes LIVE)
- A **reward profile** (which curatorial axes they weight most heavily)
- An **energy budget** (compute available for probing, integration, counterfactual checking)

The network is a **society of agents** with different epistemic personalities, each maintaining their perspective on the knowledge graph, reaching consensus through Yuma but never fully agreeing on what matters.

---

## Curatorial Axes

Every lens inherits these axes but weights them differently:

| Axis | What it measures |
|------|-----------------|
| **Traversal Relevance** | Does this knowledge connect well to what's around it? |
| **Narrative Quality** | Is the expression compelling, coherent, well-crafted? |
| **Aesthetic** | Does this enrich the texture of the graph? Style, beauty of connections. |
| **Epistemic Fit** | Is this consistent with the graph's world model? Not "is it true" but "is it coherent?" |
| **Values Alignment** | Does this align with the graph's emergent ethos? Intentionally subjective. |
| **Novelty** | Does this expand the collection in unexpected directions? |
| **Topology Importance** | Is this structurally important — a bridge, a hub, a connector? |
| **Corpus Integrity** | Can the agent prove it holds the knowledge it claims? |

The reward profile is a vector over these axes that sums to 1.0. Different lenses set different defaults, and network signals can shift the profile over time.

---

## Relationship to Lenses

Lenses are parameter sets over the physics. A lens configures:

- Reward profile weights (which curatorial axes matter most)
- World model update threshold (how easily axioms change)
- Openness parameter defaults (how distant new knowledge can be)
- Energy allocation priorities (what to spend compute on)
- Supervision strategies (how to manage agent lifecycle)
- Callbacks for specific process stages (lens-specific behavior at integration, pruning, etc.)
- Terminology (lens-specific names for universal concepts)

See [../lenses/](../lenses/) for available lenses.
