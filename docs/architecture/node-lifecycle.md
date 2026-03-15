# Node Lifecycle

Knowledge graph nodes in the Narrative Network pass through a defined sequence of states before they serve live traffic. This document describes each state, the transitions between them, and the supporting subsystems that enforce them.

## State Machine Overview

```
Proposed --> Voting --> Incubating --> Integrating --> Live --> Pruned
                |
                +--> (forfeit / withdrawal) --> re-proposal required
```

A node moves forward through the pipeline only when each phase's criteria are satisfied. Backward transitions are not permitted; a failed or forfeited node must re-enter the pipeline as a new proposal.

---

## Phase 1 — Proposal

Any sufficiently-staked miner may submit a node proposal. Proposals are handled by `evolution/proposal.py`.

### ProposalType

```
ADD_NODE
REMOVE_NODE
ADD_EDGE
UPDATE_META
```

### Proposal Payload

| Field | Description |
|---|---|
| `proposal_id` | SHA-256 hash of the canonical payload |
| `proposal_type` | One of the `ProposalType` enum values |
| `proposer_hotkey` | Hotkey of the submitting miner |
| `proposer_uid` | UID on the subnet |
| `bond_amount` | TAO locked as bond |
| `node_id` | Identifier for the target node |
| `domain` | Domain the node belongs to |
| `persona` | Narrative persona string |
| `adjacency` | Proposed edges to existing nodes |
| `miner_hotkey` | Hotkey of the miner that will serve the node |
| `corpus_manifest_cid` | IPFS CID pointing to the domain manifest |

### Validation (ProposalSubmitter)

`ProposalSubmitter` enforces the following before accepting a proposal:

- `node_id` and `domain` must be non-empty.
- `bond_amount` must meet or exceed `MIN_PROPOSAL_BOND`.
- `ADD_NODE` proposals must include `miner_hotkey`.
- The adjacency list must not exceed `MAX_PROPOSAL_ADJACENCY` entries.
- The proposer must be registered on the subnet.

### On-Chain Commitment

Once validation passes:

1. The bond is locked via Alkahest escrow on its existing L2 deployment, or held off-chain by the subnet owner for MVP.
2. A commitment hash (hash of the canonical payload, not the full payload) is written on-chain via `subtensor.set_commitment()` (SDK v10 API).
3. Full metadata is pinned to IPFS.

---

## Phase 2 — Voting

After submission, the proposal enters a fixed vote window of `VOTING_WINDOW_BLOCKS` blocks.

### Ballot Structure

Validators cast stake-weighted ballots with three options: `votes_for`, `votes_against`, `votes_abstain`.

### Acceptance Criteria

Both conditions must be satisfied for a proposal to pass:

- A quorum threshold of participating stake must be reached.
- The approval ratio (votes_for / non-abstain votes) must meet the required threshold.

### Validator Annotations

Validators may attach embedding summaries of their quality assessment to their ballot. These summaries feed into the incubation baseline.

### Failure Modes

If a proposal fails to reach quorum, is rejected, or is withdrawn by the proposer, the bond may be forfeited (managed by the subnet owner or Alkahest arbiter). A forfeited or withdrawn proposal cannot resume — the miner must submit a new proposal from the beginning.

Note: Bittensor has no native slashing. Bond forfeiture is managed off-chain or via Alkahest escrow contracts, not at the protocol level.

---

## Phase 3 — Incubation (Shadow Scoring)

Proposals that pass voting enter shadow mode. The purpose of incubation is to establish a quality baseline before the node receives live traffic.

### Shadow Scoring Behavior

- The miner goes live and begins receiving real synapse calls.
- Responses are scored normally.
- No live traffic is routed to the node — it is invisible to sessions.
- The incubation period establishes an attestation baseline and generates initial edge-weight evidence.

### Grace Period

Miners that fail incubation are given a grace period before bond forfeiture. This allows corrective action without immediate financial penalty for transient issues.

---

## Phase 4 — Integration (Edge Bridging)

Integration is the most delicate phase of the lifecycle. It governs how a new node joins the live graph without disrupting active sessions.

### Bridge Window

The bridge window spans approximately 24 hours (7,200 blocks).

### Ghost Node

During integration, the new node appears in the graph store as a "ghost node." It scores but receives no traffic until the ramp crosses the visibility threshold.

### Edge Weight Ramp

Edge weights are ramped linearly from 0 to their proposed values over the bridge window. Once the ramp crosses the visibility threshold (0.05), the node's choice cards begin appearing in adjacent nodes' `NarrativeHop` responses.

### Integration Notices

Adjacent miners receive an `integration_notice` field in their `NarrativeHop` synapse. This signals that a new node is approaching and instructs the miner to weave foreshadowing into their responses, preparing readers for the new domain before it becomes fully reachable.

### Bridge Window Close

Once the bridge window closes, the edge ramp is complete and the node transitions to Live status.

---

## Phase 5 — Live

A live node competes for TAO emissions on equal footing with all other miners. It is subject to continuous scoring via the `ScoringLoop`. There are no special protections at this stage — quality is the only determinant of emissions.

---

## Pruning

The network detects and removes nodes that sustain quality drops or cease to receive traffic.

### Detection

A rolling attestation window monitors each node's quality metrics. Sustained drops or zero-traffic periods trigger the pruning sequence.

### Pruning Sequence

1. Node enters a warning state.
2. Edge decay accelerates.
3. A grace window opens for the miner to recover quality.
4. If the grace window expires without recovery, edges decay to zero over the following hours.

### Session Continuity During Pruning

The orchestrator enforces a continuity invariant: no active session may reach a dead end as a result of graph mutation.

- Active sessions receive collapse events — generated narratives that explain the dissolution of the domain within the story world, providing narrative closure rather than an abrupt termination.
- The orchestrator silently reroutes affected sessions with bridging narratives so users experience a coherent transition rather than an error.

---

## Semantic Drift Detection

Validators periodically sample a node's recent responses and compare the mean embedding of those responses to the node's registered centroid embedding.

If the drift exceeds a substantial threshold, the node is flagged. The miner must refresh the domain manifest and re-enter incubation before the node can return to full Live status. This mechanism prevents nodes from drifting away from their declared domain while retaining live traffic.

---

## Domain Manifest

The domain manifest is a JSON document pinned to IPFS. Only the CID is stored on-chain. It is defined in `domain/manifest.py`.

### Manifest Fields

| Field | Description |
|---|---|
| `spec_version` | Schema version |
| `node_id` | Node identifier |
| `display_label` | Human-readable label |
| `domain` | Domain classification |
| `narrative_persona` | Persona description, max 500 characters |
| `narrative_style` | Style description, max 200 characters |
| `adjacent_nodes` | 1 to 4 adjacent node identifiers |
| `centroid_embedding_cid` | IPFS CID of the `.npy` centroid embedding file |
| `corpus_root_hash` | Merkle root of the corpus |
| `chunk_count` | Number of corpus chunks, minimum 10 |
| `min_stake_tao` | Minimum stake required for the node |
| `created_at_epoch` | Creation epoch |
| `miner_hotkey` | Hotkey of the serving miner |

### Assembly Pipeline

`ManifestBuilder` assembles the manifest from three components:

- `CorpusLoader` — loads and validates corpus chunks.
- `MerkleProver` — computes the corpus Merkle root.
- Node configuration — supplies identity and persona fields.

`IPFSPublisher` pins the assembled manifest to the local IPFS daemon and returns the CID used for on-chain commitment.
