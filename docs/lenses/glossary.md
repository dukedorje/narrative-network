# Lens Glossary

Maps terminology across lenses back to the primary Bittensor Knowledge Network terms.

---

## Primary Network (Canonical Terms)

These are the authoritative terms used in the codebase and Bittensor protocol.

| Primary Term | Definition |
|-------------|-----------|
| **Agent** | Any autonomous participant in the network — curator, miner, traversing entity, composed subgraph |
| **Curator** | Agent that shapes the knowledge graph through selection, scoring, integration, and pruning. Bittensor role: validator. |
| **Coherence Engine** | The system of curation processes that maintains internal consistency across the knowledge graph |
| **Lens** | A named configuration of the Coherence Engine — parameters, reward profile, callbacks, and terminology for a specific use case |
| **Knowledge graph** | The living topology of interconnected knowledge domains |
| **World model** | The set of foundational axioms that determine what *can be true* in the knowledge graph. Not the graph contents, but the rules and assumptions knowledge is evaluated against. Mutable — but updates are major events that recontextualize existing knowledge. |
| **World event** | An occurrence that updates the world model itself, not just the graph contents. Propagates through all agents, recontextualizing downstream knowledge. |
| **Observation** | The act of a curator selecting a miner's output for inclusion in the graph. Unobserved phenomena don't exist in the graph. |
| **Spanning distance** | Minimum graph distance from new knowledge to the nearest existing cluster. Measures integration difficulty. |
| **Openness parameter** | Maximum spanning distance a curator will tolerate for integration. Controls epistemic conservatism/progressivism. |
| **Counterfactual** | Knowledge that contradicts the graph's world model. May be pruned or may trigger belief axiom updates. |
| **Belief axiom** | A foundational assumption in the graph's world model. Updated when sufficient evidence demands it. |
| **Reward profile** | Mutable vector of weights across curatorial axes. Determines what the curator optimizes for. |
| **Bridge path** | Narrative/evidential connection built between existing knowledge and new knowledge during integration |
| **Membrane** | The semi-permeable boundary of a subgraph that filters incoming knowledge |
| **Composed agent** | Multiple subgraphs treated as a single agent with unified interface |
| **Sub-subnet** | A composed agent operating as a single UID on Bittensor, running internal curation |
| **Society** | The full network of agents with different epistemic personalities |
| **Node** | A knowledge domain in the graph |
| **Edge** | Weighted connection between nodes |
| **Hop** | A single traversal step |
| **Traversal** | A path through the knowledge graph |
| **Miner** | Agent that produces knowledge phenomena (corpus, narrative) |
| **Emission** | TAO reward distributed based on curatorial scoring |

---

## Cross-Lens Term Mapping

| Concept | Primary Network | Knowledge Network | Game | Composable Network |
|---------|----------------|-------------------|------|-------------------|
| Participant | Agent | Researcher | Player (human) / NPC (AI) | Subgraph / Composed agent |
| Graph shaper | Curator | Curator | Worldbuilder | Curator / Membrane |
| Knowledge structure | Knowledge graph | Knowledge graph | World | Subgraph / Composed graph |
| Foundational axioms | World model | World model | Canon / World rules | Unified belief structure |
| Axiom-level change | World event | Paradigm shift | World event (cataclysm, revelation, era change) | World model negotiation / Composition conflict |
| Source material | Corpus | Corpus / Evidence | Lore | Corpus with provenance |
| Traversal step | Hop | Query / Exploration | Scene / Action | Cross-boundary traversal |
| Path through graph | Traversal | Research trail | Story arc | Composition pathway |
| Agent's knowledge | Local knowledge graph | Research context | Memory | Subgraph |
| Inconsistency | Counterfactual | Contradiction | Plot hole | Cross-boundary conflict |
| Truth revision | Belief axiom update | Evidence update | Retcon | Composition renegotiation |
| Pre-integration hint | FORESHADOW | Pending research | Backstory / Omen | Boundary sensing |
| Integration work | BRIDGE | Collaborative bridging | Introduction / Arrival | Distributed bridge construction |
| Fully integrated | LIVE | Accepted knowledge | Canon | Composed |
| Removal | Pruning | Retraction | Forgotten lore / Collapse event | Graceful decomposition |
| Boundary permeability | Openness parameter | Openness | World consistency tolerance | Membrane permeability |
| Grouped agents | Composed agent | Research team | Faction / Party | Sub-subnet |
| Full network | Society | Research community | Story world | Network of networks |

---

## Usage Notes

- When writing code or protocol specs, always use **Primary Network** terms
- When writing user-facing docs for a specific lens, use that lens's terminology
- When discussing cross-lens concepts, use Primary Network terms with lens-specific terms in parentheses
- The glossary is the canonical mapping — if a lens introduces new terms, add them here
