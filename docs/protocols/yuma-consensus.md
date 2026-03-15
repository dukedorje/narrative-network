# Yuma Consensus and Weight Setting

## Overview

Yuma Consensus (YC) is Bittensor's mechanism for combining validator scores into a single emission distribution. It solves reward manipulation in subjective utility networks where validators independently assess miner quality.

**Security guarantee:** ~70% honest utility retains 60% honest stake under typical conditions. Requires majority honest stake.

---

## Mathematical Formulation

### Core Variables

| Variable | Equation | Description |
|----------|----------|-------------|
| W_ij | — | Validator i's weight on miner j |
| S_i | S'_i / Σ_k S'_k | Validator i's normalized stake |
| P_j | Σ_i S_i · W_ij | Miner prerank (pre-clip) |
| W̄_j | argmax_w(Σ_i S_i · {W_ij ≥ w} ≥ κ) | Consensus weight: κ-majority threshold |
| W̄_ij | min(W_ij, W̄_j) | Consensus-clipped weight |
| R_j | Σ_i S_i · W̄_ij | Miner rank (post-clip) |
| I_j | R_j / Σ_k R_k | Miner incentive (normalized rank) |
| T_j | R_j / P_j | Miner trust (fraction surviving clip) |
| T_vi | Σ_j W̄_ij | Validator trust (vtrust) |
| W̃_ij | (1−β)·W_ij + β·W̄_ij | Penalized weight for bonds |
| ΔB_ij | S_i · W̃_ij / Σ_k S_k · W̃_kj | Instant bond fraction |
| B_ij(t) | α·ΔB_ij + (1−α)·B_ij(t-1) | EMA-smoothed bond |
| D_i | Σ_j B_ij · I_j | Validator dividends |

### Epoch Computation (from subtensor epoch.rs)

```
1. Load weight matrix W from chain
2. Compute preranks: P = W^T · S
3. Compute consensus weights: W̄ = weighted_median(S, W, κ)
4. Clip weights: W̄_ij = min(W_ij, W̄_j)
5. Compute ranks: R = clipped_W^T · S
6. Compute trust: T = R / P
7. Compute vtrust: Tv = row_sum(clipped_W)
8. Normalize ranks → incentive: I = R / ΣR
9. Compute bond delta: ΔB = col_normalize(W̃ ⊙ S)
10. EMA bonds: B(t) = α·ΔB + (1−α)·B(t-1)
11. Compute dividends: D = B^T · I
12. Distribute emission: 41% miners (by I), 41% validators (by D), 18% owner
```

### Default Hyperparameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| κ (kappa) | 0.5 | 50% stake must agree on consensus weight |
| β (bonds_penalty) | 0.5–1.0 | Penalty for out-of-consensus bonding |
| α (EMA alpha) | 0.1 | 10% new bond, 90% historical |

---

## Weight Setting

### API (SDK v10)

```python
response = subtensor.set_weights(
    wallet,
    netuid=1,
    uids=[0, 1, 2],
    weights=[0.5, 0.3, 0.2],
    mechid=0,
    version_key=version_as_int,
    max_attempts=5,
    wait_for_inclusion=True,
    wait_for_finalization=True
)
```

### Weight Processing Pipeline

Before on-chain submission, weights pass through `process_weights_for_netuid()`:

1. **min_allowed_weights** — minimum miners that must receive non-zero weight
2. **max_weight_limit** — per-validator per-miner cap; normalized so no single weight exceeds limit
3. **Quantile filtering** — weights below threshold zeroed out
4. **Integer conversion** — float32 → u16 (0–65535), internally summing to MAX_INT_WEIGHT

### Timing Constraints

| Constraint | Default | Description |
|------------|---------|-------------|
| `WeightsRateLimit` | 100 blocks (~20 min) | Min blocks between submissions |
| `ActivityCutoff` | 5000 blocks (~16.7h) | Max inactivity before exclusion |
| `Tempo` | 360 blocks (~72 min) | Epoch length |

---

## Commit-Reveal (v4 — Drand Automatic)

### Purpose

Prevents weight copying by making weights cryptographically inaccessible for a configurable number of tempos.

### How It Works (Current v4)

1. Validator calls `set_weights()` normally
2. Chain encrypts weights using **Drand time-lock encryption**
3. Encrypted weights committed on-chain — publicly visible but unreadable
4. After `commit_reveal_period` tempos, Drand beacon fires and provides decryption key
5. Weights automatically decrypted and enter next Yuma Consensus epoch

**No manual commit/reveal steps needed with v4.** Just call `set_weights()`.

### Legacy Manual API (pre-v4)

```python
# Step 1: Commit
response = subtensor.commit_weights(
    wallet, netuid=1, salt=[1, 2, 3, 4],
    uids=[0, 1, 2], weights=[0.5, 0.3, 0.2], mechid=0
)

# Step 2: Reveal (after commit_reveal_period tempos)
response = subtensor.reveal_weights(
    wallet, netuid=1, uids=[0, 1, 2],
    weights=[0.5, 0.3, 0.2], salt=[1, 2, 3, 4]
)
```

### Subnet Configuration

```
CommitRevealWeightsEnabled = True    # enable (subnet owner sets)
CommitRevealPeriod = 1               # tempos before reveal
```

Constraint: `ImmunityPeriod` (blocks) must exceed `CommitRevealPeriod × Tempo` blocks.

---

## Anti-Collusion: Three Layers

### Layer 1 — Vtrust Penalty (Always Active)

Vtrust = Σ_j W̄_ij. A copier submitting stale weights sees W_ij diverge from current W̄_j, lowering vtrust → lower dividends.

### Layer 2 — Bond EMA Memory (Always Active)

EMA bonds reward **early discovery** of high-performing miners. Copiers who bond after discovery get permanently smaller bond shares.

### Layer 3 — Commit-Reveal (Opt-in)

Encrypts weights for N tempos. Copiers only see stale weights. Effective when miner performance changes between tempos.

---

## Liquid Alpha (Consensus-Based Bonds)

When `liquid_alpha_enabled = True`, the EMA α varies per validator-miner pair:

- `alpha_high`: α when validator weight matches consensus (fast bond accumulation)
- `alpha_low`: α when validator deviates from consensus (slow accumulation)

Rewards precise consensus alignment.

---

## Implications for Narrative Network

### Our Scoring Maps to Weight Setting

Our four-axis scoring (traversal 0.40, quality 0.35, topology 0.25, corpus variable) produces a combined score per miner. This score becomes the weight we set via `set_weights()`.

Yuma Consensus then:
- Clips our weights against other validators' weights (κ-majority)
- Computes bonds based on alignment with consensus
- Distributes emission proportional to consensus-weighted ranks

### What We Control vs What Protocol Controls

| Aspect | Who Controls |
|--------|-------------|
| Individual miner scores | Our validator logic |
| Score combination into weights | Our validator logic |
| Weight clipping / consensus | Yuma Consensus (protocol) |
| Emission split (41/41/18) | Protocol (fixed) |
| Within-miner emission distribution | Yuma Consensus (by weight rank) |

### Key Design Constraint

Our emission model (45% traversal, 30% quality, 15% topology, 10% reserve) must be implemented **within the weight-setting logic**, not as separate emission pools. The actual TAO distribution is entirely determined by the weights we set — Yuma Consensus handles the rest.

This means: our "pools" are really **weighting strategies** applied when computing the final per-miner score that becomes the weight value.

---

## Sources

- [opentensor/subtensor consensus.md](https://github.com/opentensor/subtensor/blob/main/docs/consensus.md)
- [Commit Reveal](https://docs.learnbittensor.org/concepts/commit-reveal)
- [Weight Copying Problem](https://docs.learnbittensor.org/concepts/weight-copying-in-bittensor)
- [Subnet Hyperparameters](https://docs.learnbittensor.org/subnets/subnet-hyperparameters)
- [Consensus-Based Weights / Liquid Alpha](https://docs.bittensor.com/subnets/consensus-based-weights)
