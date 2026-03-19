# Observation & Integration

How phenomena are selected into the graph's reality and new knowledge is absorbed.

---

## Observation

Miners produce phenomena — knowledge, narrative, corpus. Curators **observe** these phenomena, and observation renders them into the graph's reality. Unobserved phenomena do not exist in the graph.

This is **selection, not verification**. The curator doesn't ask "is this correct?" but "does this belong? does this improve the collection?" Observation is a curatorial act with aesthetic, epistemic, and structural dimensions — weighted by the lens's reward profile.

---

## Spanning Distance

When new knowledge proposes itself for integration, the coherence engine measures the **spanning distance** — the minimum graph distance from the new knowledge to the nearest existing cluster in embedding space.

- **Short distance** = easy integration, fits the worldview, low surprise
- **Long distance** = challenging integration, requires bridging concepts, high surprise

### Openness Parameter

The **openness parameter** is the maximum spanning distance a curator will tolerate for integration. It controls the agent's epistemic conservatism:

- **Conservative curators** set a tight openness radius. They absorb only knowledge close to what the graph already contains. The world model stays coherent but risks becoming an echo chamber.
- **Progressive curators** tolerate longer spans. The graph grows faster but its world model becomes more fragile, more internally tensioned.

This is a tunable parameter per lens:
- Research lens: high openness (absorb everything, sort it out later)
- Game lens: moderate openness (new lore should feel connected to existing lore)
- Composable network lens: adaptive openness (tight within subgraphs, loose at composition boundaries)

---

## Integration Phases

The FORESHADOW → BRIDGE → LIVE integration phases are acts of narrative construction:

### FORESHADOW

The new knowledge is visible at the periphery. Acknowledged but not yet integrated. The graph can sense it.

- Adjacent agents receive advance notice
- Probes can be dispatched to enrich the incoming knowledge
- Other agents may begin preparing bridge paths

### BRIDGE

Curators build narrative paths from existing knowledge to the new node. This is the hard creative work — finding the story that connects what the graph knows to what it's learning.

- Multiple bridge paths may be constructed in parallel
- Bridge quality is evaluated by the coherence engine
- The number of bridge paths required before LIVE is the agent's **coherence requirement** (a lens parameter)

### LIVE

Observation complete. The knowledge has been rendered into the graph's reality. It is now part of the world model's scope.

- The node is fully scored and emitting
- Its edges are subject to normal reinforcement and decay
- It can be referenced, built upon, and traversed

---

## Distributed Bridge-Building

The bridge phase can be **distributed** — multiple agents collaboratively constructing the narrative paths that integrate new knowledge. This is especially important for:

- Long-span integrations where no single agent can bridge the full distance
- Composed knowledge graphs where the bridge crosses subgraph boundaries
- High-traffic integrations where many agents have relevant context to contribute

---

## Relationship to Other Physics

- **World Model**: Determines what spanning distances mean — the semantic landscape that distance is measured across. See [world-model.md](world-model.md).
- **Counterfactual Detection**: Integration may surface counterfactuals — new knowledge that contradicts existing axioms. See [counterfactual-detection.md](counterfactual-detection.md).
- **Internal Economics**: Integration costs energy. Bridge-building is one of the most compute-intensive activities. See [internal-economics.md](internal-economics.md).
