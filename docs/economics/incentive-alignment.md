# Incentive Alignment

Bittensor Subnet 42 — Narrative Network

---

## The Fundamental Problem

How do you evaluate a knowledge mutation when you don't have ground truth for novel knowledge recombination?

Standard reward signals assume a known correct answer. The Narrative Network operates in the space of novel synthesis — recombining existing knowledge chunks into new narrative passages. There is no oracle. You cannot score a mutation against the right answer because the right answer does not exist prior to the act of mutation.

The solution is comparative attestation. Multiple miners produce competing mutations at each node. Validators rank them relative to attractors — centroid embeddings that define the semantic basin of each knowledge cluster — rather than against absolute truth. The best mutation wins not because it matches a ground truth but because it best serves the attractor basin, as judged by an independent panel of validators whose weights are aggregated via Yuma Consensus.

This reframes evaluation from verification to curation, and it makes the scoring honest without requiring a trusted oracle.

---

## Miner Incentives

### Domain Miners

Domain miners serve chunk retrieval. Their job is to maintain a corpus, respond to traversal queries accurately and quickly, and commit a corpus Merkle root via `set_commitment()` that binds them to the contents of that corpus.

Revenue: Domain miners earn from the protocol's 41% miner emission share, proportional to their validator-assigned weight. Their weight is determined by four scoring axes (traversal 0.40, quality 0.30, topology 0.15, corpus integrity 0.15). Domain miners naturally score highest on traversal quality (they serve the chunks being evaluated) and corpus integrity (they commit Merkle roots).

The competitive pressure is structural. Multiple miners register per node. A miner serving stale, slow, or falsified chunks receives lower weights from validators → lower emission share. If a miner's Merkle root is challenged and found inconsistent, validators assign zero corpus score → near-zero overall weight → zero emission → eventual deregistration when the UID slot is needed.

Centroid embeddings define the attractor basin for each node. Domain miners must maintain corpora coherent with the node's centroid. A corpus that drifts from the centroid will fail quality scoring even if the Merkle root is technically valid.

### Narrative Miners

Narrative miners author knowledge mutations. They receive the source chunks from domain miners and produce narrative passages that synthesize, extend, or recombine that knowledge.

Revenue: Same 41% miner emission share, weighted by validator scores. Narrative miners naturally score highest on quality (they generate the passages being evaluated) and benefit from topology scoring if they serve structurally important nodes.

The alignment is direct: the miner that writes the best passage receives the highest weight and the largest emission share. There is no split between "doing the work" and "getting paid for the work."

This creates compounding pressure toward quality. A narrative miner that consistently produces top-scoring passages accumulates more emission, generating revenue that funds better infrastructure and models, which produces higher scores, which earns more emission. The convexity is intentional.

### Penalty Mechanics (No Native Slashing)

Bittensor does not have protocol-level slashing. Our enforcement uses weight-based penalties:

- **Zero weight = zero emission**: Validators assign zero/near-zero weight to misbehaving miners
- **Economic death**: Sustained zero emission makes continued operation unprofitable
- **Deregistration**: When all UID slots are full, new registrants replace the lowest-emission neuron

This is sufficient for corpus fraud, quality drops, semantic drift, and inactivity. For proposal bonds, the subnet owner manages bond lifecycle off-chain or via Alkahest escrow (see below).

---

## Validator Incentives

Validators earn from the protocol's 41% validator+staker emission share. Their earnings are determined by Yuma Consensus:

- **Bond dividends**: Proportional to how well their weights align with consensus (high alignment → large bond → large dividend)
- **vtrust**: Sum of consensus-clipped weights. Higher vtrust → more earnings
- **Staker delegation**: Nominators can stake to validators, increasing their consensus influence. Validators earn a configurable commission (default 18%)

Going offline means exclusion from the epoch (activity cutoff at 5,000 blocks). This is not a penalty — it is simply the absence of work. A validator that does not score does not contribute to Yuma Consensus and earns nothing.

### Honest Scoring Enforcement

Scoring honesty is enforced by Yuma Consensus at the protocol level:

1. **κ-majority clipping**: Any validator weight that exceeds what 50% of stake supports gets clipped. A minority cabal setting inflated weights sees those weights reduced to consensus levels.

2. **Bond penalty**: Out-of-consensus validators earn lower bond shares → lower dividends. Consistently deviating validators lose influence and income.

3. **Commit-reveal v4**: Weights are encrypted via Drand time-lock encryption for `CommitRevealPeriod` tempos. Copiers only see stale weights, which produces vtrust penalties when miner rankings change between tempos.

4. **EMA bonds**: Reward early discovery of high-performing miners. Copiers who bond after discovery get permanently smaller shares.

No custom BFT quorum is needed. Yuma Consensus provides stronger guarantees with less implementation complexity.

### Graph Infrastructure

Validators maintain the graph store as a condition of accurate scoring:
- Updating edge weights after each traversal
- Logging traversal paths to the session ledger
- Running edge weight decay between epochs
- Detecting and flagging centroid drift
- Computing betweenness centrality for topology scoring

This is infrastructure work, not optional. Validators that fail to maintain graph state produce inaccurate topology scores → lower consensus alignment → lower vtrust → lower dividends.

---

## Structural Incentives — The Topology Axis

The topology scoring axis (weight: 0.15) pays bridge nodes based on betweenness centrality, independent of traffic volume.

A node that sits between two otherwise disconnected knowledge clusters earns topology score every epoch, regardless of whether many players traverse it. This matters for two reasons:

1. It rewards structural contributions that would otherwise be undercompensated. A bridge between a niche chemistry cluster and a materials science cluster may serve rare but high-value traversal paths. Without topology rewards, that bridge is not economically rational to build.

2. It gives new entrants a viable entry strategy. An established hub miner has accumulated high traversal and quality scores. A new miner cannot compete head-to-head. But a new miner can identify two distant knowledge clusters with no connecting path and propose a bridge node. The topology axis pays based on structural position, not traffic history.

The topology axis is the answer to the question of how new miners compete against established hubs. They do not compete at the same nodes. They extend the graph into underserved regions.

---

## Attack Vectors and Defenses

### Corpus Fabrication

A domain miner fabricates corpus contents that pass casual inspection but do not actually support the claimed knowledge domain.

Defense: Merkle root stability challenges. Validators periodically re-query random chunks against the committed Merkle root. A corpus that changes between commitment and challenge fails. Fabricated corpora that lack internal consistency fail coherence scoring when narrative miners attempt to generate grounded passages from them. Result: zero corpus score → near-zero weight → zero emission.

### Quality Score Gaming

A narrative miner attempts to optimize against the scoring function rather than producing genuinely high-quality synthesis.

Defense: Comparative scoring. The miner is not scored against a fixed rubric but against competing miners at the same node. Gaming a comparative ranking requires understanding and beating all competitors simultaneously. Yuma Consensus's κ-majority clipping means any scoring anomaly requires corrupting 50%+ of validator stake, not just one validator.

### Sybil Nodes

An attacker registers many low-quality nodes to capture topology rewards or dilute honest scoring.

Defense: Bond requirements at registration. Incubation period before a new node earns traversal credits. Registration burn cost (dynamic, set by Bittensor). A sybil attack requires burning TAO at each registration plus bonding stake at each node, making it expensive to scale and economically irrational against the expected topology scores from a sparse, poorly-connected sybil cluster.

### Centroid Drift

A miner gradually drifts its corpus away from its committed centroid to shift the node's knowledge domain toward more profitable territory without triggering an immediate penalty.

Defense: Periodic drift detection. Validators measure centroid consistency across epochs. Drift beyond a threshold triggers a forced manifest refresh and re-incubation, during which the node earns reduced weight. The cost of re-incubation makes drift unprofitable unless the new centroid is substantially more valuable, at which point an honest re-registration is the rational path.

### Collusion Between Miners

A domain miner and narrative miner collude to inflate scores for low-quality passages.

Defense: Multiple validators independently score each passage. No single validator's score determines the outcome. Yuma Consensus aggregates across all validators with κ-majority clipping. Collusion between miners does not affect validator scoring unless validators are also colluding, which requires corrupting 50%+ of validator stake simultaneously.

### Proposal Spam

A miner floods the system with low-quality node proposals to occupy registration slots or dilute topology rewards.

Defense: Bond forfeiture for failed or slashed proposals. A proposal that fails incubation scoring loses its bond (managed by subnet owner). Registration burn cost creates an additional cost floor. Spam proposals are self-funding attacks only if the bond + burn is smaller than expected topology rewards, which bond sizing is calibrated to prevent.

---

## Alkahest Integration — Settlement Layer

Alkahest is deployed on an existing efficient L2. We use it there — not redeployed on Subtensor EVM — to avoid maintenance burden and fragmentation.

### Integration Points

**Proposal bonds** are the primary Alkahest integration. Bonds are locked via Alkahest escrow on its existing L2. The validator set acts as arbiter — confirming incubation quality and authorizing bond release or forfeiture. The subnet owner funds bond returns (with 5% bonus for successful proposals) from the 18% owner emission share.

**Domain manifests** can be expressed as Alkahest obligations with algorithmic arbiters checking corpus integrity (Merkle root verification, centroid embedding validation). The manifest is the agreement. The arbiter is the verification logic. The bond is the escrow.

**EAS attestations** provide an audit trail. Key economic events — proposal outcomes, epoch scores, corpus challenges — are recorded as Ethereum Attestation Service attestations on the L2. This creates an auditable history independent of Bittensor's metagraph.

### Why Not Subtensor EVM?

Alkahest is already deployed and battle-tested on an efficient L2. Redeploying on Subtensor EVM would:
- Add a second deployment to maintain
- Fragment the Alkahest ecosystem
- Require bridging TAO to the EVM layer for escrow

Instead, we use lightweight off-chain coordination between the subnet and Alkahest's existing deployment. Proposal bonds can be denominated in stablecoins or bridged TAO on the L2. The Bittensor protocol handles TAO emission natively — Alkahest handles settlement and attestation where it already lives.

---

## The Compounding Effect

Quality earners compound:

Higher TAO earnings fund better hardware and models. Better models produce higher-quality narrative passages. Higher scores earn more weight from validators. More weight generates more emission. More emission produces higher TAO earnings.

This convexity is intentional. The network should reward quality escalation, not just participation. A miner that produces consistently top-scoring passages should earn disproportionately more than one producing median passages. The quality axis creates this gradient.

The topology axis provides the structural counterbalance. A miner that cannot yet compete at the quality frontier can contribute structurally — extending the graph, bridging isolated clusters, earning topology-weighted emission that funds the infrastructure needed to eventually compete on quality.

New entrants do not need to beat established hubs. They need to find the edges of the graph where they can contribute structurally first, then build toward quality competition as their position strengthens.

---

## Subnet Economic Health Under dTAO

Our subnet's total emission depends on net TAO staking inflows (dTAO Taoflow model). To attract stakers:

1. **Demonstrate consistent miner quality** — high-quality traversals and knowledge graph growth signal a healthy subnet
2. **Maintain high validator vtrust** — signals honest, well-functioning scoring
3. **Alpha token appreciation** — as TAO inflows grow, alpha price rises, rewarding existing stakers
4. **Bittensor Foundation support** — we may receive initial TAO and assistance launching the subnet

Negative net flow = zero emissions. Staker confidence is existential for the subnet's survival.
