# EVM Integration: Alkahest/EAS on Subtensor

## Overview

Bittensor has **full EVM compatibility** since October 2024. Solidity contracts run unmodified on the Subtensor chain. This enables us to deploy Alkahest escrow, arbiter, and fulfillment contracts directly on Subtensor — no external bridge needed for core settlement.

---

## Subtensor EVM Specs

| Parameter | Value |
|-----------|-------|
| Chain ID | 945 (mainnet) |
| RPC | Standard Ethereum JSON-RPC compatible |
| MetaMask | Supported |
| Address format | h160 (Ethereum-style) on EVM; ss58 on Substrate |

### Precompiles (Bittensor-Specific)

| Precompile | Address | Purpose |
|------------|---------|---------|
| Staking V2 | `0x0000000000000000000000000000000000000805` | `addStake` / `removeStake` |
| Subnet | `0x0000000000000000000000000000000000000803` | 50+ subnet management functions |
| ED25519 Verify | available | Signature verification for ss58 accounts |

### Address Bridging

- EVM uses h160 (Ethereum-style) addresses
- Substrate uses ss58 addresses
- Transfer between them via bridge or `withdraw` extrinsic in EVM pallet
- When a smart contract calls the staking precompile, the **contract address** becomes the coldkey

---

## Alkahest Integration Architecture

### On-Chain Components (Deploy to Subtensor EVM)

```
┌─────────────────────────────────────────────────┐
│                 Subtensor EVM                    │
│                                                  │
│  ┌──────────────────┐  ┌──────────────────────┐ │
│  │ TraversalEscrow   │  │ ProposalBondEscrow   │ │
│  │ (per-hop credits) │  │ (node proposals)     │ │
│  └────────┬─────────┘  └──────────┬───────────┘ │
│           │                       │              │
│  ┌────────▼───────────────────────▼──────────┐  │
│  │           ValidatorArbiter                 │  │
│  │  (checks quality scores, quorum, proofs)   │  │
│  └────────┬───────────────────────┬──────────┘  │
│           │                       │              │
│  ┌────────▼─────────┐  ┌─────────▼───────────┐ │
│  │ HopFulfillment    │  │ ManifestFulfillment  │ │
│  │ (EAS attestation) │  │ (EAS attestation)    │ │
│  └──────────────────┘  └─────────────────────┘  │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │          Staking Precompile (0x805)       │   │
│  │  addStake / removeStake for collateral    │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### 1. Traversal Credits as Escrow Obligations

Each completed hop creates an escrow obligation:

```solidity
contract TraversalEscrow is BaseEscrowObligation {
    struct HopObligation {
        bytes32 sessionId;
        uint256 hopIndex;
        address minerHotkey;
        uint256 qualityThreshold;  // min score for release
        uint256 amount;            // TAO in RAO
    }

    function _lockEscrow(bytes data, address from) internal {
        // Lock TAO for this hop
    }

    function _releaseEscrow(bytes escrowData, address to, bytes32 fulfillmentUid) internal {
        // Release TAO to winning miner when validator confirms quality
    }

    function _returnEscrow(bytes data, address to) internal {
        // Return TAO if hop not fulfilled within timeout
    }
}
```

### 2. Proposal Bonds as Alkahest Escrows

```solidity
contract ProposalBondEscrow is BaseEscrowObligation {
    struct ProposalBond {
        bytes32 nodeId;
        bytes32 manifestCid;      // IPFS CID
        bytes32 merkleRoot;       // corpus Merkle root
        uint256 bondAmount;
        uint256 votingDeadline;
    }

    // Bond lifecycle:
    // Success (incubation passed): return bond × 1.05
    // Lapse (no quorum):          return bond × 0.95
    // Slash (fraud detected):     return 0
}
```

### 3. Validator Arbiter

```solidity
contract ValidatorArbiter is IArbiter {
    function checkObligation(
        bytes32 escrowUid,
        bytes calldata demand,
        bytes32 fulfillmentUid
    ) external view returns (bool) {
        // Check: quality score meets threshold
        // Check: validator quorum attestations exist
        // Check: no fraud flags
    }
}
```

### 4. EAS Attestations for Audit Trail

Every economic event recorded as an EAS attestation:

```solidity
// Schema: session_id, hop_index, miner_uid, quality_score, timestamp
bytes32 attestationUid = eas.attest(AttestationRequest({
    schema: HOP_SCHEMA_UID,
    data: AttestationRequestData({
        recipient: minerAddress,
        data: abi.encode(sessionId, hopIndex, qualityScore),
        revocable: false
    })
}));
```

---

## Staking Precompile Usage

For locking TAO as collateral in escrow contracts:

```solidity
interface IStakingV2 {
    function addStake(bytes32 hotkey, uint16 netuid, uint256 amount) external;
    function removeStake(bytes32 hotkey, uint16 netuid, uint256 amount) external;
}

// Amount in RAO (1 TAO = 1e9 RAO)
IStakingV2(0x0000000000000000000000000000000000000805).addStake(
    hotkey, netuid, amount
);
```

---

## Cross-Chain Considerations

### If EAS Must Be on Ethereum Mainnet

If Alkahest's EAS deployment is on Ethereum (not Subtensor):
1. Deploy attestation contracts on Subtensor EVM (primary)
2. Use a relay/bridge pattern to mirror attestations to Ethereum EAS
3. vTAO (bridged TAO) token exists for cross-chain use cases

### Recommended Approach

Deploy everything on **Subtensor EVM first**:
- Avoids cross-chain complexity
- Native TAO access via staking precompile
- Same security model as the subnet itself
- Can add Ethereum bridging later if needed

---

## On-Chain Storage Alternatives

Bittensor also provides simpler on-chain metadata storage:

```python
# Store metadata hash on-chain (lightweight, no EVM needed)
subtensor.set_commitment(wallet, netuid=1, data="ipfs://QmManifestCID")

# Substrate storage queries
substrate.query('SubtensorModule', 'Axons', [netuid, hotkey])
substrate.query('SubtensorModule', 'CRV3WeightCommits', [netuid, hotkey])
```

For simple manifest CIDs and Merkle roots, `set_commitment()` may suffice. Reserve EVM contracts for settlement logic requiring programmatic escrow/arbitration.

---

## Chain Events

Subtensor emits standard Substrate events:

```python
from substrateinterface import SubstrateInterface

substrate = SubstrateInterface(url="wss://entrypoint-finney.opentensor.ai:443")

def event_handler(obj, update_nr, subscription_id):
    for event in obj['params']['result']['events']:
        if event['event_id'] == 'StakeAdded':
            print(event)

substrate.subscribe_block_headers(event_handler)
```

Epoch timing formula: `(block_number + netuid + 1) % (tempo + 1) == 0`

---

## Recommended Approach: Use Alkahest on Its Existing L2

Alkahest is already deployed and battle-tested on an efficient L2. **We recommend using it there, not redeploying on Subtensor EVM.** Reasons:

- Avoids maintaining a second Alkahest deployment
- No ecosystem fragmentation
- Alkahest team maintains the L2 contracts
- Broader ecosystem access (other projects using Alkahest)

The Subtensor EVM option remains available if future requirements demand native TAO escrow without bridging, but for MVP and likely beyond, the existing L2 deployment is sufficient.

### What We Use Subtensor EVM For

Reserve EVM for future needs that genuinely require on-chain TAO logic:
- If native TAO escrow becomes necessary (no bridging)
- If atomic stake + escrow operations are needed
- If the Alkahest team deploys natively on Subtensor

### What We Use Alkahest's Existing L2 For

- Proposal bond escrow and arbitration
- EAS attestation trail for economic events
- Domain manifest obligations with algorithmic arbiters

### What We Use Subtensor Natively For

- `set_commitment()` for manifest CIDs and Merkle roots (lightweight, no EVM needed)
- `set_weights()` for emission distribution (core protocol)
- Metagraph queries for UID discovery and stake information

## Implementation Phases

### Phase 1: Off-Chain Settlement (MVP)
- Validators mediate all settlement
- Manifest CIDs stored via `set_commitment()`
- Proposal bonds managed by subnet owner off-chain
- No EVM or Alkahest contracts needed
- Fastest path to working subnet

### Phase 2: Alkahest Integration (Testnet)
- Proposal bonds locked via Alkahest escrow on existing L2
- Validators act as Alkahest arbiters for bond release/forfeit
- EAS attestations for proposal lifecycle
- Bonds denominated in stablecoins or bridged TAO on L2

### Phase 3: Full Settlement Layer (Mainnet)
- Complete EAS audit trail for all economic events
- Optional per-hop attestations for traversal quality
- Dashboard querying Alkahest attestations for subnet economics transparency

---

## Sources

- [Bittensor EVM Smart Contracts](https://docs.learnbittensor.org/evm-tutorials)
- [EVM on Bittensor](https://blog.bittensor.com/evm-on-bittensor-draft-6f323e69aff7)
- [Staking Precompile](https://docs.learnbittensor.org/evm-tutorials/staking-precompile)
- [Subnet Precompile](https://docs.learnbittensor.org/evm-tutorials/subnet-precompile)
- [Token Bridging / vTAO](https://docs.learnbittensor.org/evm-tutorials/bridge-vtao)
- [Subtensor Storage Queries](https://docs.learnbittensor.org/subtensor-nodes/subtensor-storage-query-examples)
- [Alkahest Protocol Docs](https://www.arkhai.io/docs)
