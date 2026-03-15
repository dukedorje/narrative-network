# Arkhai / Alkahest Protocol

**Source:** https://www.arkhai.io/docs
**Tagline:** Programmable markets for compute, energy, and information

## Overview

Alkahest is an open-source protocol for **peer-to-peer agreements on-chain**, built on top of **EAS** (Ethereum Attestation Service). The name references the alchemical "universal solvent" — it dissolves centralized market structures into atomic, composable peer-to-peer exchanges.

Traditional platforms bundle negotiation, scheduling, settlement, and quality control into centralized monopolies. Alkahest breaks these apart into **modular, composable smart contract primitives** that anyone can use to build custom peer-to-peer markets.

## Core Architecture

The protocol has three building blocks: **Escrow Contracts**, **Arbiter Contracts**, and **Fulfillment Contracts**.

### Escrow Contracts (Obligations)

Lock a commitment — usually tokens, but can be **any on-chain action** — that gets released when a demand is fulfilled.

**Lifecycle:**

1. **Lock** (`_lockEscrow`) — Secure the asset/commitment and validate preconditions
2. **Wait** — Someone needs to fulfill the demand
3. **Release** (`_releaseEscrow`) — Demand met: execute the escrowed action (pay out tokens, cast a vote, etc.)
4. **Return** (`_returnEscrow`) — Demand not met and escrow expired: return assets to the creator

Escrow contracts inherit from `BaseEscrowObligation` and register an attestation schema with EAS. Each escrow specifies an **arbiter** and a **demand** — these define the conditions for release.

**Implementation pattern:**

```solidity
struct ObligationData {
    address token;
    uint256 amount;
    address arbiter;
    bytes demand;
}
```

Key methods to implement:
- `_lockEscrow(bytes data, address from)` — validate and secure
- `_releaseEscrow(bytes escrowData, address to, bytes32 fulfillmentUid)` — execute on fulfillment
- `_returnEscrow(bytes data, address to)` — handle expiration cleanup

Important: the escrow contract is `msg.sender` during lock/release/return — user-initiated actions (like token approvals) must happen in separate transactions.

### Arbiter Contracts

Arbiters answer one question: **"Has the demand been satisfied?"**

They implement `IArbiter` with a `checkObligation()` method returning true/false. Types include:

| Type | Description |
|------|-------------|
| **Trusted oracle** | A human or service signs off on fulfillment |
| **Cryptographic** | Verify a signature, hash preimage, or proof |
| **Algorithmic** | Check on-chain state programmatically |

The arbiter is specified at escrow creation time, so both parties know the rules upfront.

### Fulfillment Contracts

Create **attestations** (via EAS) representing completed work or delivered results. Three patterns:

#### Pattern 1: StringObligation (Generic)

Stores arbitrary string data. Validation handled entirely by external arbiters.

```solidity
StringObligation.ObligationData memory resultData = StringObligation
    .ObligationData({ item: "72F, sunny" });

bytes32 fulfillmentUid = stringObligation.doObligation(resultData, escrowUid);
```

**Use when:** prototyping, simple text results, off-chain validation, evolving data formats.

#### Pattern 2: Specialized Contracts (No IArbiter)

Domain-specific contracts enforce structure through typed fields and helper functions while delegating validation to separate arbiters.

```solidity
struct ObligationData {
    string endpoint;
    string method;
    uint16 statusCode;
    string headers;
    string body;
    uint256 timestamp;
}
```

Includes on-chain query helpers like `isSuccessfulCall()` and `matchesEndpoint()`.

**Use when:** production systems needing consistent data formats, on-chain queryability, multiple validation criteria.

#### Pattern 3: Combined Obligation + IArbiter

Bundles validation directly into the fulfillment contract when there's an inherent, canonical validation method.

```solidity
contract CryptoSignatureObligation is BaseObligation, IArbiter {
    function checkObligation(...) external pure override returns (bool) {
        // Verify signature matches expected signer
    }
}
```

**Use when:** cryptographic signatures, hash preimages, mathematical proofs — where validation is fundamental to the data's meaning.

## Typical Flow

```
1. Alice creates escrow: "I'll pay 100 USDC to whoever does X"
   → specifies arbiter + demand

2. Bob does the work, submits a fulfillment attestation

3. Arbiter checks: does Bob's fulfillment satisfy Alice's demand?

4a. Yes → Bob calls collectEscrow() → gets paid
4b. No / expired → Alice reclaims her tokens
```

Everything is recorded as **attestations on EAS**, providing a transparent, verifiable trail.

## Key Properties

- **Composable** — mix and match escrow types, arbiters, and fulfillment contracts
- **Beyond tokens** — escrows can lock any on-chain action (votes, permissions, state changes)
- **Flexible validation** — from oracle approvals to cryptographic proof verification
- **Open-source public good** — infrastructure, not a platform that takes a cut
- **SDK support** — TypeScript, Rust, and Python client libraries

## Arkhai Product Suite

- Escrow & Arbitration (core protocol)
- Natural Language Agreements
- Git Commit Marketplace
- Agentic RAG
- Cybernetic Agents

## Relevance to Narrative Network

Alkahest could serve as the settlement and agreement layer for narrative-related exchanges — enabling peer-to-peer agreements around content, compute, or information with programmable arbitration and on-chain attestation trails.
