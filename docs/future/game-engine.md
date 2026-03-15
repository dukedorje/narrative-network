# Game Engine Layer — Future Vision

**Built on top of the attestation network, not instead of it.**

This layer treats the living knowledge graph as a simulation substrate. Everything here depends on the comparative attestation layer being operational first — the game engine consumes attestations, it doesn't replace them.

---

## The Simulation Reframe

Once the attestation network is running, a second interpretation becomes available: the evaluation criteria — cosine distance from centroid, coherence scoring, edge utility — are the **physics of a simulation**. Distance from centroid isn't "did you stay on topic," it's "how far did this entity travel through its local phase-space this step." The hallucination budget IS the simulation step size. Validators aren't just attestation engines — they become the laws of motion.

The combined phase-space of every trajectory across every node is the simulation space. Each traversal is a probe through possibility-space. The narrative isn't just a mutation mechanism — it's how the simulation steps forward through time.

---

## Entities and Personas

The graph becomes a game board populated by multiple kinds of traversing entities:

**Soul Tokens** — a user's entry submission places them in the graph. The submission is their identity vector. Two users who submit similar knowledge tokens enter near each other; wildly different submissions start in distant regions. Your knowledge determines your starting position.

**NPCs as Autonomous Probes** — non-player entities that traverse the graph on their own trajectories, driven by their own persona embeddings. They explore paths that human users don't, preventing the graph from collapsing into only human-popular routes. They are the network's curiosity — probes sent into the unmapped edges of the knowledge space.

**Persona Embedding Spaces** — each entity (player or NPC) carries its own embedding context that evolves as it traverses. The persona drifts through embedding space with each hop, accumulating the knowledge mutations it has witnessed. Two entities that started at the same node but took different paths end up in measurably different regions of persona-space.

---

## The Graph as Game Board

The graph IS the game board, rendered live. Story cards float over nodes, branches illuminate as you traverse them.

**Aesthetic:** Dark cosmic / neural-organic — like navigating a living mind. Deep space blacks with bioluminescent node colors, glitch accents, ancient-map-meets-neural-net vibes.

**Live Rendering:** A D3 force-simulation (or equivalent) with real-time weight updates. Players see the graph breathe — edges thickening as others traverse them, new nodes fading in during integration, dying nodes flickering during pruning. The topology is never static on screen.

**Choice Cards:** At each node, the narrative passage is accompanied by choice cards that float over adjacent nodes. Each card carries a thematic color, a destination, and an edge weight delta. The player's choice is a vote on the graph's topology — every hop reinforces the edge taken and decays the alternatives.

---

## Simulation Dynamics

**Stepping Forward Through Time:** Each NarrativeHop is a discrete time step in the simulation. The LLM's natural tendency to hallucinate — to generate plausible continuations that weren't in the training data — is the mechanism by which the simulation explores futures. Hallucination, bounded by attractor basins and scored by validators, becomes controlled speculation. The network simulates many possibilities, going on within the embedding space of its personas.

**Multi-Entity Phase Space:** The combined trajectories of all entities — players, NPCs, automated probes — map out a phase-space. The graph's edge weights at any moment are a cross-section of this space: a snapshot of which transitions between knowledge domains have been explored and attested. Over time, the phase-space reveals structure that no single traversal could: clusters of commonly-traversed paths, isolated domains that only NPCs visit, phase transitions where a new node's integration reorganizes traffic patterns.

**Emergent Lore:** Each narrative miner independently authors passages with only local context — its persona, the traversal path, retrieved chunks. Yet the coherence scoring forces these independent authors toward narrative consistency. A shared mythology emerges that no single entity wrote. An AI-generated, economically-incentivized, collectively-validated body of lore that evolves with the knowledge it encodes.

---

## Memorable Moments from Graph Mutation

The attestation layer's graph evolution protocol produces events that become powerful game moments:

**Foreshadowing:** During node integration, adjacent miners receive notices about new domains crystallizing nearby. They weave hints into their passages — "distant rumours of a new domain of thought at the edge of the graph." Players experience new knowledge regions forming in real time.

**Collapse Events:** When a node is pruned, active sessions there receive a generated passage:

> *The realm fractures. The knowledge held here loses coherence — validators withdraw their stake, the corpus hashes go dark one by one. You feel the edges of this place dissolving. Before it disappears entirely, you glimpse the next domain in the distance.*

**Bridge Narratives:** When a player's path is rerouted due to pruning, the destination miner generates a "fault line passage" — the player was heading somewhere that no longer exists, and the narrative justifies the redirect. These become some of the most memorable moments: the sensation that the knowledge graph is alive and unstable, that domains can be born and die, and that your path through it is genuinely contingent.

---

## TAO Micropayments per Hop

Each traversal step triggers a micropayment. Players spend TAO to move through the graph, and that TAO flows to the miners whose mutations were attested as valuable. This creates a direct economic loop: knowledge that people want to traverse earns more. The game economy and the attestation economy are the same economy.

---

## What This Layer Adds

The attestation network produces: comparative evaluations of knowledge mutations, compressed into a living graph topology.

The game engine layer adds: the experience of *being inside* that process. Entities with persistent identities traversing the graph, witnessing its evolution, and feeling the consequences of its mutation dynamics as narrative events. The simulation framing turns infrastructure events (node integration, pruning, drift correction) into plot.

The game engine doesn't change what the network computes. It changes what it feels like to participate.
