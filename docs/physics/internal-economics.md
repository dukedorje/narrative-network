# Internal Economics

How agents budget compute and decide what to spend energy on.

---

## The Energy Model

Probing costs compute. Hole detection costs compute. Bridge-building costs compute. Counterfactual grooming costs compute. Every agent has a finite **energy budget** and must decide what to spend it on.

Each agent (node, curator, composed subgraph) has:

- **Energy** — a replenishing resource representing available compute/attention
- **Energy income** — determined by the agent's emission share (TAO earned → energy to spend)
- **Energy cost** — each action (probe, integration evaluation, bridge-building, counterfactual check) has a cost
- **Energy allocation** — the agent's strategy for spending its budget across competing priorities

This creates a feedback loop: agents that earn more (by serving good knowledge) get more energy to improve their knowledge, which helps them earn more. But energy must be spent wisely — a node that probes constantly but never integrates the results wastes its budget.

---

## Priority Allocation

An agent's energy allocation is a lens parameter. Different lenses prioritize different uses of compute:

| Priority | Knowledge Network | Game | Composable Network |
|----------|-------------------|------|-------------------|
| Hole detection | High — finding gaps is the primary mission | Low — holes are "unexplored territory," part of the world | Moderate — holes at composition boundaries matter |
| Probing | High — research is the point | Low — the world generates from within | Moderate — probing other subgraphs |
| Bridge-building | Moderate — evidence chains take energy | High — narrative paths are the product | High — composition requires bridges |
| Counterfactual checking | Moderate — contradictions are tracked, not urgently resolved | High — plot holes break immersion | High — cross-boundary conflicts need attention |
| World model maintenance | Low — world model rarely changes | Moderate — world events need coherence propagation | High — composed world models need constant negotiation |

---

## Bittensor Integration Questions

Key questions for how this maps to Bittensor's existing infrastructure:

1. **Internal weight-setting**: Can a composed agent (sub-subnet) run its own internal Yuma consensus, or does it need to be a fully registered subnet? What's the minimum viable unit of internal economic governance?

2. **Compute metering**: Bittensor doesn't currently meter compute per-miner — it only measures output quality. The energy model would need to be implemented at the application layer, tracking compute spent per agent within the subnet's own validator.

3. **Hierarchical emissions**: If a sub-subnet earns TAO as a single UID, how does it distribute internally? This is the internal economics problem — the sub-subnet is itself a small economy.

4. **Inter-subnet probing**: Can probes query other subnets? Bittensor has cross-subnet communication in its roadmap but current implementation is limited. For now, probes would need to use external APIs (like unbrowse) rather than native Bittensor calls.

5. **Registration costs**: Bittensor charges TAO for UID registration. If agents within a composed subgraph need UIDs, the registration cost creates a floor on the granularity of the internal economy.

---

## Relationship to Existing Systems

- **Emission pools** → already implement internal economics at the miner level; this extends it to the agent/node level with compute budgeting
- **Edge decay** → already implements a simple energy model (edges that aren't "fed" by traversals lose energy)
- **Integration phases** → already implement a bridge-building pipeline; this adds energy cost and supervision to that pipeline

---

## Relationship to Other Physics

- **Supervision**: The supervision system manages *how* energy is spent — scheduling, lifecycle, failure recovery. See [supervision.md](supervision.md).
- **Hole Detection**: Hole detection and probing are major energy consumers. The probe budget is the key economic constraint on exploration. See [hole-detection.md](hole-detection.md).
- **Counterfactual Detection**: Grooming the graph for contradictions requires compute proportional to graph complexity. See [counterfactual-detection.md](counterfactual-detection.md).
