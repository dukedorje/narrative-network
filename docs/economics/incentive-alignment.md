# Incentive Alignment

Bittensor Subnet 42 — Narrative Network

---

## The Fundamental Problem

How do you evaluate a knowledge mutation when you don't have ground truth for novel knowledge recombination?

Standard reward signals assume a known correct answer. The Narrative Network operates in the space of novel synthesis — recombining existing knowledge chunks into new narrative passages. There is no oracle. You cannot score a mutation against the right answer because the right answer does not exist prior to the act of mutation.

The solution is comparative attestation. Multiple miners produce competing mutations at each node. Validators rank them relative to attractors — centroid embeddings that define the semantic basin of each knowledge cluster — rather than against absolute truth. The best mutation wins not because it matches a ground truth but because it best serves the attractor basin, as judged by an independent panel of validators under BFT quorum.

This reframes evaluation from verification to curation, and it makes the scoring honest without requiring a trusted oracle.

---

## Miner Incentives

### Domain Miners

Domain miners serve chunk retrieval. Their job is to maintain a corpus, respond to traversal queries accurately and quickly, and stake against a corpus Merkle root that commits them to the contents of that corpus.

Revenue sources:
- Traversal pool: 35% of traversal emission for serving chunks used in active sessions
- Quality bonus: 25% of quality pool for corpus accuracy and retrieval speed

The competitive pressure is structural. Multiple miners register per node. A miner serving stale, slow, or falsified chunks loses traversal credits to better competitors. If a miner's Merkle root is challenged and found inconsistent with the actual corpus — via random chunk re-queries against the committed root — the miner is slashed. The stake is not decorative. It is the bond that makes the corpus commitment credible.

Centroid embeddings define the attractor basin for each node. Domain miners must maintain corpora coherent with the node's centroid. A corpus that drifts from the centroid will fail quality scoring even if the Merkle root is technically valid.

### Narrative Miners

Narrative miners author knowledge mutations. They receive the source chunks from domain miners and produce narrative passages that synthesize, extend, or recombine that knowledge.

Revenue sources:
- Traversal pool: 65% of traversal emission for passages used in active sessions
- Quality bonus: 75% of quality pool for passages that score highly against validators

The alignment is direct: the miner that writes the best passage wins the session and the traversal credit. There is no split between "doing the work" and "getting paid for the work." A high-quality passage earns both the session win and the ongoing traversal credit every time a player traverses that node.

This creates compounding pressure toward quality. A narrative miner that consistently produces top-quartile passages accumulates traversal credits across many epochs, generating revenue that funds better infrastructure and models, which produces higher scores, which wins more sessions. The convexity is intentional.

### Stake Requirements

Both miner types stake against their domain manifests. Manifests must be honest:
- Corpus Merkle roots must reflect actual corpus contents (challenged by random re-queries)
- Centroid embeddings must be accurate (validated against the stored corpus)
- Node metadata must be consistent with registered state

A manifest that fails integrity checks triggers slash conditions. The stake is sized to make falsification economically irrational.

---

## Validator Incentives

Validators score narrative passages and maintain the graph store. They earn from the quality pool: 20% of total emission, distributed proportional to scoring volume.

Going offline means zero quality pool earnings. This is not a penalty — it is simply the absence of work. A validator that does not score does not contribute to the curation layer and earns nothing from it. The 30% of total emission that flows through the quality pool is only accessible through active participation.

### Honest Scoring Enforcement

Scoring honesty is enforced by peer quorum. A validator that scores outlier from quorum loses its weight contribution for that round. Weight commits require BFT quorum acknowledgement before they are applied. A validator that consistently scores against quorum loses influence in the aggregate scoring, which reduces its revenue share.

This is comparative scoring, not absolute scoring. No validator needs to know the ground truth. Each validator independently ranks the competing mutations at a node. The quorum is over rankings, not absolute scores. Collusion requires coordinating rankings across multiple independent validators simultaneously, which the BFT threshold is designed to make expensive.

### Graph Infrastructure

Validators maintain the graph store as a condition of participation:
- Updating edge weights after each traversal
- Logging traversal paths to the session ledger
- Running edge weight decay between epochs
- Detecting and flagging centroid drift

This is infrastructure work, not optional. Validators that fail to maintain graph state lose validator standing. The quality pool pays for both scoring work and graph maintenance — they are inseparable functions.

Validator trust ultimately derives from root network Yuma consensus. The subnet's internal BFT quorum operates on top of this foundation.

---

## Structural Incentives — The Topology Pool

The topology pool pays bridge nodes based on betweenness centrality, independent of traffic volume.

A node that sits between two otherwise disconnected knowledge clusters earns topology rewards every epoch, regardless of whether many players traverse it. This matters for two reasons:

1. It rewards structural contributions that would otherwise be undercompensated. A bridge between a niche chemistry cluster and a materials science cluster may serve rare but high-value traversal paths. Without topology rewards, that bridge is not economically rational to build.

2. It gives new entrants a viable entry strategy. An established hub miner has accumulated traversal credits, reputation, and optimized infrastructure. A new miner cannot compete head-to-head against that. But a new miner can identify two distant knowledge clusters with no connecting path and propose a bridge node. The topology pool pays immediately based on structural position, not traffic history.

The topology pool is the answer to the question of how new miners compete against established hubs. They do not compete at the same nodes. They extend the graph into underserved regions.

---

## Attack Vectors and Defenses

### Corpus Fabrication

A domain miner fabricates corpus contents that pass casual inspection but do not actually support the claimed knowledge domain.

Defense: Merkle root stability challenges. Validators periodically re-query random chunks against the committed Merkle root. A corpus that changes between commitment and challenge fails. Fabricated corpora that lack internal consistency fail coherence scoring when narrative miners attempt to generate grounded passages from them.

### Quality Score Gaming

A narrative miner attempts to optimize against the scoring function rather than producing genuinely high-quality synthesis.

Defense: Comparative scoring. The miner is not scored against a fixed rubric but against competing miners at the same node. Gaming a comparative ranking requires understanding and beating all competitors simultaneously. Peer quorum on validator weights means any scoring anomaly requires coordinated validator collusion, not just one validator's participation.

### Sybil Nodes

An attacker registers many low-quality nodes to capture topology pool rewards or dilute honest scoring.

Defense: Bond requirements at registration. Incubation period before a new node earns traversal credits. Minimum stake enforced by the manifest system. A sybil attack requires bonding stake at each node, making the attack expensive to scale and economically irrational against the expected topology rewards from a sparse, poorly-connected sybil cluster.

### Centroid Drift

A miner gradually drifts its corpus away from its committed centroid to shift the node's knowledge domain toward more profitable territory without triggering an immediate slash.

Defense: Periodic drift detection. Validators measure centroid consistency across epochs. Drift beyond a threshold triggers a forced manifest refresh and re-incubation, during which the node earns no traversal credits. The cost of re-incubation makes drift unprofitable unless the new centroid is substantially more valuable than the old one, at which point an honest re-registration is the rational path.

### Collusion Between Miners

A domain miner and narrative miner collude to inflate scores for low-quality passages that use the domain miner's chunks.

Defense: Multiple validators independently score each passage. No single validator's score determines the outcome. BFT quorum is required for weight commits. Collusion between miners does not affect validator scoring unless validators are also colluding, which requires corrupting a BFT-threshold fraction of the validator set simultaneously.

### Proposal Spam

A miner or validator floods the system with low-quality node proposals to occupy registration slots or dilute topology rewards.

Defense: Bond forfeiture for failed or slashed proposals. A proposal that fails incubation scoring or is slashed for manifest fraud forfeits its bond. Spam proposals are self-funding attacks only if the bond is smaller than the expected topology reward, which the bond sizing is calibrated to prevent.

---

## Arkhai / Alkahest Integration — Settlement Layer

The Alkahest escrow-arbiter-fulfillment pattern maps naturally onto the subnet's economic flows.

Alkahest defines agreements as natural language obligations with algorithmic arbiters. An arbiter is a contract or program that evaluates whether an obligation has been fulfilled and releases escrow accordingly. This maps to several subnet mechanisms:

**Traversal credits** accrue as escrow obligations during a session. The validator quorum acts as the arbiter — confirming traversal quality and authorizing credit release at epoch close. Credits that fail validation do not settle.

**Domain manifests** are natural language agreements (a miner commits to maintaining a corpus coherent with a centroid) with algorithmic arbiters (Merkle root verification, centroid embedding validation). The manifest is the agreement. The arbiter is the verification logic. The stake is the escrow.

**Proposal bonds** are escrow with a multi-validator arbiter. A node proposal bonds stake. The arbiter evaluates whether the node passes incubation successfully (quality scores above threshold, manifest integrity intact). If the proposal succeeds, bond returns. If slashed, bond forfeits. Alkahest SDK tooling — available in TypeScript, Rust, and Python — can handle the bond lifecycle programmatically, reducing integration overhead for miner operators.

**EAS attestations** provide the on-chain audit trail. Every economic event — traversal credit accrual, quality score commit, slash event, epoch settlement — is recorded as an Ethereum Attestation Service attestation. This creates an auditable history that does not depend on any single party's record-keeping.

The Alkahest integration is not cosmetic. It provides a settlement layer with defined semantics for obligation, fulfillment, and dispute, which the subnet's internal mechanisms produce but do not themselves record with on-chain finality.

---

## The Compounding Effect

Quality earners compound:

Higher TAO earnings fund better hardware and models. Better models produce higher-quality narrative passages. Higher scores win more session competitions. More session wins generate more traversal credits. More traversal credits produce higher TAO earnings.

This convexity is intentional. The network should reward quality escalation, not just participation. A miner that produces consistently top-quartile passages should earn disproportionately more than one producing median passages. The quality pool's concentration toward high scorers creates this gradient.

The topology pool provides the structural counterbalance. A miner that cannot yet compete at the quality frontier can contribute structurally — extending the graph, bridging isolated clusters, earning topology rewards that fund the infrastructure needed to eventually compete on quality. The two pools define two valid paths into the network's economic structure.

New entrants do not need to beat established hubs. They need to find the edges of the graph where they can contribute structurally first, then build toward quality competition as their position strengthens.
