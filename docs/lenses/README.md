# Lenses

A **lens** is a named configuration of the [Coherence Engine](../physics/README.md): a set of parameters, reward profiles, callbacks, and terminology that tunes the network for a specific use case. The curation stages remain the same across lenses; what changes is *how* each stage behaves and *what* it optimizes for.

---

## What a Lens Configures

A lens is a parameter set over the [physics](../physics/). It configures:

- **Reward profile weights** — which curatorial axes matter most (see [physics/README.md](../physics/README.md#curatorial-axes))
- **World model update threshold** — how easily axioms change (see [physics/world-model.md](../physics/world-model.md))
- **Openness parameter defaults** — how distant new knowledge can be (see [physics/observation-and-integration.md](../physics/observation-and-integration.md))
- **Energy allocation priorities** — what to spend compute on (see [physics/internal-economics.md](../physics/internal-economics.md))
- **Supervision strategies** — how to manage agent lifecycle (see [physics/supervision.md](../physics/supervision.md))
- **Counterfactual policy** — how contradictions are resolved (see [physics/counterfactual-detection.md](../physics/counterfactual-detection.md))
- **Callbacks** for specific process stages — lens-specific behavior at integration, pruning, etc.
- **Terminology** — lens-specific names for universal concepts

A lens **cannot** violate the physics. It tunes them.

---

## Available Lenses

| Lens | Primary Use Case | Doc |
|------|-----------------|-----|
| **Knowledge Network** | Research, collaborative knowledge building | [knowledge-network.md](knowledge-network.md) |
| **Game** | Narrative generative experiences, NPCs, interactive fiction | [game.md](game.md) |
| **Composable Network** | Distributed bridging, sub-subnets, graph composition | [composable-network.md](composable-network.md) |

---

## Terminology

See [glossary.md](glossary.md) for terminology mappings between lenses and the primary Bittensor network.
