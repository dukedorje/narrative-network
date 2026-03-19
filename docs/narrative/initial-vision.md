# Bittensor Knowledge Network (BKN)

**The network that thinks by being traversed.**

A Bittensor-powered living knowledge graph where LLM hallucination is harnessed as the mechanism for generating knowledge mutations. The network doesn't store knowledge — it grows it. Miners produce competing mutations of knowledge at each node. Validators generate comparative attestations of those mutations. The attestations are the product. Reward flows to nodes whose mutations are attested as valuable.

---

## The Core Insight: Comparative Attestation

You cannot evaluate a knowledge mutation against ground truth — there is none for novel knowledge recombination. So the network evaluates *comparatively*: multiple miners produce competing mutations at each node, and validators rank them.

But even comparative ranking needs a reference frame. That's what **attractors** provide. Each node's centroid embedding defines an attractor basin — not "the right answer," but the gravitational center of what this node is *about*. A mutation that stays near the attractor is conservative. One that drifts far is exploratory. Validators attest to which mutations are valuable *relative to the attractor*, without needing perfect knowledge of what the mutation should have been.

These comparative attestations, accumulated over time and compressed into edge weights, **are** the knowledge the network produces. Not the narratives. Not the corpus chunks. The ranked, stake-weighted judgments of which knowledge mutations, at which nodes, along which edges, were worth reinforcing.

The narrative isn't a wrapper around the network. **The narrative is how the network evolves** — each passage is a mutation, each traversal is a path through the space of possible mutations, and each attestation is the network's verdict on which mutations to keep.

---

## Aesthetic Direction

Dark cosmic / neural-organic — like navigating a living mind. Deep space blacks with bioluminescent node colors, glitch accents, ancient-map-meets-neural-net vibes. The graph IS the interface, rendered live. Branches illuminate as they are traversed.

---

## System Architecture

The core concept maps onto Bittensor's primitives. Each node in the knowledge graph corresponds to a miner on a custom subnet. Miners maintain a living body of knowledge on a domain (consensus theory, emergent systems, temporal memory, etc.) and earn TAO by serving two functions simultaneously: **knowledge retrieval** and **narrative authoring**. Validators generate comparative attestations — scoring competing mutations and committing the results to chain.

When an entity enters the graph via a soul token — any knowledge submission — it gets embedded and cosine-compared against every node's domain centroid. The top-k matching nodes define the entry cluster and opening narrative. As the entity traverses the graph, each hop triggers competing miners to produce mutations. The validator attests which mutation best serves the traversal — grounded in the node's corpus, coherent with the path so far, and connected to real adjacent nodes.

The living graph evolves because every traversal path is logged as a weighted edge reinforcement. Paths taken often become canonical routes that the subnet converges around. Paths unexplored decay in weight — collective forgetting. New knowledge injected by miners can fracture existing paths and spawn entirely new narrative branches.

### Synapse Types

The subnet speaks three message types:

**KnowledgeQuery** — the retrieval synapse. On entry, the orchestrator embeds the soul token and fires this to all miners simultaneously. Each miner scores the query against its domain centroid and returns its top-k document chunks with a similarity score. Validators rank miners by relevance, diversity, and factual groundedness against the miner's registered corpus hash.

**NarrativeHop** — the traversal synapse, the heart of the mutation loop. Each traversal step fires this to the destination node's competing miners. Each miner holds a narrative context — its domain persona, its corpus, the full traversal path so far. Each produces a competing mutation: a narrative passage, a set of choice branches pointing to adjacent nodes, and a knowledge synthesis. The validator's comparative attestation of these competing mutations is what gets committed to chain.

**WeightCommit** — the attestation synapse, internal to validators. After sampling NarrativeHop responses from competing miners, the validator scores them comparatively and commits the attestation to the metagraph.

### Miner Registration

Miners register by staking TAO against a **domain manifest**: a declaration of their node ID, corpus (content-addressed chunk hashes), domain centroid embedding, and narrative persona. The manifest is stored off-chain in a content-addressable store with only the CID on-chain. Validators verify corpus integrity by sampling random chunks and checking them against the manifest's Merkle tree. Miners that falsify their corpus are slashed.

---

## Validator Attestation — Evaluation Without Omniscience

The fundamental problem: how do you evaluate a knowledge mutation when you don't have perfect knowledge of what the mutation should produce?

You keep a **parallel set of mutations** — multiple miners competing for the same node, each producing a different response — and you evaluate them against **attractors**, not against ground truth. The attractor (centroid) doesn't tell you the right answer. It tells you the shape of the basin this node occupies in embedding space, and lets you judge how each mutation moves through that basin.

Validators attest on three axes:

**Groundedness** — is the mutation supported by the miner's actual corpus? The validator embeds the passage and compares it to the miner's registered knowledge. Mutations that drift into unregistered domains score near zero. The attractor keeps each node honest about what it knows.

**Coherence** — continuity across the traversal. The new passage must be continuous with what came before while moving meaningfully toward the destination domain's attractor. This is what makes traversal *through* the graph meaningful rather than random — each step must be a legible transition between attractor basins.

**Edge Utility** — are the proposed next-branches valid? Destinations must exist in the live metagraph with active miners. Weight deltas must be bounded to prevent manipulation. You can't hallucinate edges to nodes that don't exist.

The comparative attestation — "miner A's mutation scored higher than miner B's, relative to these attractors" — is the atomic unit of value the network produces. Everything else (the narratives, the graph topology, the edge weights) is downstream of accumulated attestations.

---

## Graph Memory — Reinforcement and Decay

The living knowledge graph is maintained as a persistent edge-weight matrix. Every traversal reinforces the edges crossed and triggers a decay pass on alternatives from the source node. This gives the graph organic memory:

- Heavily-traveled paths become **canonical routes** — knowledge connections the network has collectively attested through use
- Rarely-used paths **atrophy** — collective forgetting, but with a floor weight that prevents total disappearance
- New knowledge injected by miners can **fracture** existing paths and spawn new branches

The graph is not a static map. It is compressed attestation history. The topology at any moment is the network's best collectively-attested theory of how knowledge domains relate to each other.

---

## VM Orchestration

Three VM archetypes compose the network:

**Domain Miner** — the corpus worker. Each instance is staked to one node. It loads its domain corpus into a vector store, computes its centroid embedding, and serves retrieval queries. A secondary endpoint serves chunk-by-hash for validator Merkle challenges.

**Narrative Miner** — the mutation generator. It runs a language model tuned to the domain's persona. The fine-tuning dataset is seeded from the corpus plus authored lore establishing the domain's voice. It maintains traversal context so responses are continuous across sessions. On each hop it assembles a prompt from persona, prior narrative, traversal path, and retrieved chunks, then generates the passage and branch choices.

**Validator** — the attestation engine. At each epoch it samples active sessions, replays their last NarrativeHop against all miners registered to the destination node, generates comparative attestations, and commits weights to chain. Validators also maintain the graph store — updating edge weights and logging traversal events after scoring.

A **Gateway** faces the network, owns session state, and translates between external calls and the subnet's synapse protocol. It embeds soul tokens, routes to miners, selects highest-attested responses, and streams results. The internal synapse protocol is never exposed directly.

---

## Graph Evolution — The Lifecycle of Knowledge

The knowledge graph has a complete evolutionary lifecycle. Nodes are born through collective judgment, prove themselves before taking live traffic, enter the narrative gracefully, earn their continued existence through attestation quality, and dissolve without breaking traversals already in motion.

### Phase 1 — Proposal

Any sufficiently-staked miner can propose a new node by submitting a domain manifest, proposed edges to existing nodes, sample narrative responses, and a bond. The bond is returned if the proposal passes; forfeited if it fails or is slashed for spam. Proposed edges have bounded initial weights — new nodes cannot enter as dominant hubs.

### Phase 2 — Voting

Validators cast stake-weighted ballots during a fixed vote window. Quorum and approval thresholds must both be met. Validators may attach an embedding summarizing their quality assessment of the narrative samples, which informs incubation scoring.

### Phase 3 — Incubation

A passed proposal enters shadow mode. The miner goes live and receives real synapse calls, but responses are scored without routing live traffic to the node. Incubation verifies stability, establishes an attestation baseline, and generates initial edge-weight evidence. Miners that fail incubation get one grace period to fix issues before bond forfeiture.

### Phase 4 — Integration

The most delicate phase. Edge weights ramp linearly from zero to their proposed values over a bridge window. Adjacent nodes receive integration notices and begin weaving **foreshadowing** into their narrative passages — signals that a new domain is crystallizing nearby. By the time the edge weight crosses the visibility threshold and branch choices start appearing, the narrative has already primed for the new node's arrival. New attractor basins don't appear instantaneously — they fade in, and the existing graph fabric absorbs them organically.

### Phase 5 — Live, Pruning, and Drift

Live nodes compete for TAO like any other miner. Nodes that stop earning their place are pruned:

- A rolling attestation window detects sustained quality drops or zero traffic
- Warning state triggers accelerated edge decay
- A grace window allows recovery before pruning
- Pruning is gradual — edges decay to zero over hours, giving active sessions time to complete

When a node is pruned, active sessions at that node receive a **collapse event** — a generated narrative explaining that the domain has dissolved — and are offered traversal to adjacent live nodes. The orchestrator enforces a **continuity invariant**: no active session ever reaches a dead end due to graph mutation. Sessions whose horizons are affected by pruning get silently rerouted with bridging narratives.

**Semantic drift detection** keeps nodes honest over long timescales. Periodically, validators sample recent responses from a node and compare their mean embedding to the node's registered centroid. Nodes that have substantially drifted from their declared attractor must refresh their manifest and re-enter incubation. The attractor basins must remain calibrated — otherwise the comparative attestations lose their reference frame, and the network can no longer evaluate what it's producing.

---

## What the Network Builds

The product is not content. It is **comparative attestation at scale** — a continuously-generated, stake-weighted record of which knowledge mutations, at which nodes, along which edges, were judged most valuable relative to their attractors.

The graph topology is compressed attestation history. The edge weights encode which transitions between knowledge domains the network has collectively validated. The attractors encode what each domain means. The narrative is the mechanism that generates mutations for the network to evaluate.

Knowledge is a living system. This network is the substrate it lives on.
