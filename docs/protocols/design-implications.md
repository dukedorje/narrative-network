# Design Implications: Bittensor Realities vs. Our Architecture

This document captures critical differences between our original architecture assumptions and how Bittensor actually works as of early 2025. These must be addressed before implementation.

---

## 1. Emission Model Redesign Required

### Original Design
Four separate emission pools: Traversal (45%), Quality (30%), Topology (15%), Reserve (10%).

### Bittensor Reality
The protocol enforces a fixed **41/41/18 split**: 41% miners, 41% validators+stakers, 18% subnet owner. There are no configurable emission pools.

### Resolution
Our "pools" become **weight-setting strategies** within the validator's scoring logic. The weights we assign to miners determine how the 41% miner share is distributed:

```
Final miner weight = (
    0.45 × traversal_score +     # traversal pool equivalent
    0.30 × quality_score +        # quality pool equivalent
    0.15 × topology_score +       # topology pool equivalent
    0.10 × corpus_integrity       # replaces reserve pool
)
```

The 18% owner share can fund the "proposal reserve" concept — bonds returned to successful proposers from the owner's revenue stream, managed off-chain or via EVM contracts.

The 10% "reserve" pool doesn't map to protocol-level emission. Instead, we use the owner's 18% take to fund proposal bond returns, operational costs, and governance.

---

## 2. No Native Slashing

### Original Design
Corpus fraud triggers "slash conditions" with bond forfeiture.

### Bittensor Reality
No protocol-level slashing exists. The only penalty is receiving zero weights → zero emissions → eventual deregistration.

### Resolution
Two-tier approach:
1. **Weight-based penalty** (native): Validators assign zero weight to fraudulent miners. Zero weight = zero emission = economic death + eventual deregistration.
2. **EVM escrow slashing** (optional, Phase 2+): Deploy escrow contracts on Subtensor EVM where proposal bonds are locked. Validator arbiter contracts can forfeit bonds on fraud detection.

For MVP, weight-based penalty is sufficient. EVM contracts add trustless enforcement later.

---

## 3. BFT Quorum Simplified by Yuma Consensus

### Original Design
Custom BFT quorum: validators hash commits, broadcast to peers, wait for acknowledgements before calling `set_weights()`.

### Bittensor Reality
Yuma Consensus already provides Byzantine-fault-tolerant weight aggregation:
- Each validator independently sets weights
- κ-majority (50% stake) consensus clips outlier weights
- Bond penalty punishes deviators
- Commit-reveal v4 (Drand) prevents weight copying automatically

### Resolution
**Remove custom BFT quorum.** Each validator independently runs its scoring pipeline and calls `set_weights()`. Yuma Consensus handles the aggregation. This is simpler and more aligned with how every other subnet works.

The `WeightCommit` dataclass in our architecture doc becomes an internal validator data structure — not a consensus protocol message.

---

## 4. dTAO Changes Subnet Economics

### Original Design
Emission allocated by root network validators.

### Bittensor Reality (Post Feb 2025)
Emission allocated by **net TAO staking flows** with EMA smoothing. Our subnet must attract and retain stakers to receive emission.

### Implications
- Subnet health directly tied to staker confidence
- Alpha token appreciation rewards long-term stakers
- We need to demonstrate clear, measurable value to attract TAO inflows
- Negative net flow = zero emissions = subnet death spiral

### Action Items
- Build clear metrics dashboard showing subnet utility (traversals, knowledge quality, graph growth)
- Design staker value proposition: alpha token appreciation + validator dividends
- Consider targeted outreach to TAO holders explaining our value proposition

---

## 5. Commit-Reveal is Automatic

### Original Design
Manual commit → reveal weight-setting protocol with timing management.

### Bittensor Reality
Commit-reveal v4 uses **Drand time-lock encryption**. Validators just call `set_weights()` — the chain handles encryption and automatic reveal.

### Resolution
Simply enable `CommitRevealWeightsEnabled = True` on our subnet and call `set_weights()` normally. No custom commit-reveal logic needed.

---

## 6. mechid Enables Dual Scoring Mechanisms

### New Opportunity
SDK v10 introduces `mechid` — subnets can run up to 2 independent incentive mechanisms.

### Potential Use
- `mechid=0`: Score domain miners (knowledge retrieval quality)
- `mechid=1`: Score narrative miners (passage generation quality)

This cleanly separates our two miner types into independent scoring tracks with separate weight matrices. Worth investigating for cleaner incentive design.

---

## 7. Alkahest: Use Existing L2, Not Subtensor EVM

### Original Design (protocols doc)
Deploy Alkahest escrow/arbiter/fulfillment contracts on Subtensor EVM.

### Revised Decision
Use Alkahest on its **existing L2 deployment**. Redeploying on Subtensor EVM adds maintenance burden, fragments the Alkahest ecosystem, and provides marginal benefit since our core emission is handled by the Bittensor protocol natively.

### What Goes Where
- **Subtensor native**: `set_weights()`, `set_commitment()`, metagraph queries — core protocol
- **Alkahest L2**: Proposal bond escrow, EAS attestations, arbiter contracts — settlement layer
- **Off-chain (MVP)**: Bond management by subnet owner — fastest path to launch

### Why Not Subtensor EVM?
- Alkahest is already deployed and battle-tested on an efficient L2
- No second deployment to maintain
- Alkahest team maintains the L2 contracts
- Native TAO access isn't needed — bonds can use stablecoins or bridged TAO
- Can revisit if future requirements demand atomic TAO escrow

---

## 8. Gateway Architecture Clarification

### Original Design
Gateway as a separate component translating REST/WebSocket to synapse protocol.

### Bittensor Reality
The gateway is essentially a validator with a user-facing API. It uses `Dendrite` to query miners via synapses, same as any validator.

### Resolution
The gateway should be a **validator node with an HTTP API layer**. It:
- Runs the full validator scoring pipeline
- Serves REST/WebSocket endpoints for users
- Uses `Dendrite` to query miners
- Sets weights based on its scoring

This avoids a separate "gateway" role that doesn't participate in consensus. If we want a non-validator gateway (for users who don't stake), it operates as a lightweight client that relays through a validator.

---

## 9. Topology Score via Metagraph, Not Custom Graph

### Consideration
Our topology score uses betweenness centrality from KùzuDB. But the Bittensor metagraph also has its own graph structure (UIDs, weights, bonds).

### Resolution
Keep KùzuDB for our domain knowledge graph (nodes = knowledge domains, edges = narrative connections). This is separate from the Bittensor metagraph (nodes = miners/validators, edges = weights/bonds).

Our topology score measures structural importance **in the knowledge graph**, not in the Bittensor network graph. These are complementary.

---

## 10. SDK v10 Migration Checklist

Must use throughout codebase:

- [ ] PascalCase imports: `Subtensor`, `Wallet`, `Axon`, `Dendrite`, `Synapse`
- [ ] Balance objects: `tao(amount)`, `rao(amount)` — no raw floats
- [ ] ExtrinsicResponse handling: check `.success`, `.message`, `.data`
- [ ] Address params: `hotkey_ss58`, `coldkey_ss58`, `destination_ss58`
- [ ] `set_commitment()` not `commit()`
- [ ] `mechid=0` parameter on weight operations
- [ ] Python ≥3.10

---

## 11. Revised Architecture Summary

```
                        User HTTP/WS
                             │
                    ┌────────▼────────┐
                    │   Validator +    │
                    │   Gateway API    │  ← Combined role
                    │   (Dendrite)     │
                    └───┬────────┬────┘
                        │        │
           KnowledgeQuery│        │NarrativeHop
                        │        │
              ┌─────────▼──┐  ┌──▼──────────┐
              │ Domain      │  │ Narrative    │
              │ Miners      │  │ Miners       │
              │ (Axon)      │  │ (Axon)       │
              └─────────────┘  └──────────────┘

Scoring: Validator sets weights via set_weights()
         Yuma Consensus aggregates across validators
         Protocol distributes: 41% miners, 41% validators, 18% owner

Settlement (Phase 2+):
         EVM contracts on Subtensor for proposal bonds + escrow
         EAS attestations for audit trail
```

---

## Priority Order for Implementation

1. **Protocol definitions** (`protocol.py`): KnowledgeQuery + NarrativeHop synapses
2. **Miner base**: Domain miner with Chroma + Merkle, Narrative miner with LLM
3. **Validator scoring**: Four-axis scoring → combined weight
4. **Local testnet**: End-to-end traversal on devnet
5. **Gateway API**: REST/WebSocket layer on validator
6. **Testnet deployment**: Real miners, real validators, real scoring
7. **EVM contracts**: Proposal bonds, escrow (Phase 2)
8. **Mainnet**: Subnet registration, production deployment

---

## Sources

All sources referenced in the individual protocol documents:
- [bittensor-sdk-v10.md](./bittensor-sdk-v10.md)
- [subnet-registration.md](./subnet-registration.md)
- [yuma-consensus.md](./yuma-consensus.md)
- [dynamic-tao.md](./dynamic-tao.md)
- [synapse-implementation.md](./synapse-implementation.md)
- [evm-integration.md](./evm-integration.md)
- [validator-miner-patterns.md](./validator-miner-patterns.md)
