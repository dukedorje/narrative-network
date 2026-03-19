# Dynamic TAO (dTAO) Economics

**Activated:** February 13–14, 2025
**Updated:** November 2025 (Taoflow model)

dTAO replaces the old root-network validator voting system with a market-driven, stake-based subnet valuation model.

---

## Core Mechanism: AMM Pools

Each subnet maintains two on-chain liquidity reserves:
- **TAO reserve** (τ_in) — TAO locked in the pool
- **Alpha reserve** (α_in) — subnet-specific token

Alpha price is determined by the reserve ratio:

```
Price = τ_in / α_in
```

Example: 1,000 TAO against 16,000 alpha = 0.0625 TAO per alpha.

---

## Alpha Tokens

- Each subnet has its own alpha token with a **21M supply cap** and same halving schedule as TAO
- When you stake TAO into a subnet validator, TAO is exchanged via the AMM for alpha tokens
- Unstaking converts alpha back to TAO through the pool
- Alpha price appreciates as more TAO flows in (TAO reserve grows relative to alpha)

---

## Emission Flow (Taoflow Model, Nov 2025)

Subnet emissions are determined by **net TAO flows** (staking minus unstaking), not token prices:

```
Block Emission: 0.5 TAO/block (post-halving Dec 2025)
     │
     ▼
Net Flow Calculation per subnet (staking - unstaking)
     │
     ▼
EMA Smoothing (86.8-day window, 30-day half-life)
     │
     ▼
Proportional allocation to subnets
(negative net flow = zero allocation)
     │
     ▼
Per Subnet: TAO injected into TAO reserve + Alpha emitted
     │
     ▼
At end of each Tempo (~360 blocks), accumulated alpha distributed:
     │
     ├──→ 18% to Subnet Owner
     │
     ├──→ 41% to Miners (by Yuma Consensus incentive score)
     │
     └──→ 41% to Validators + their Stakers
                │
                ├──→ TAO stakers: proportional share emitted as TAO
                │    (via alpha-to-TAO swap through pool)
                │
                └──→ Alpha stakers: remaining share as alpha tokens
```

### Key Properties

- Subnets with **net outflows** (more unstaking than staking) receive **zero emissions**
- Linear normalization: 2× the flow = 2× the emissions
- 86.8-day EMA smoothing prevents gaming via flash-staking
- Alpha outstanding grows as subnet emits → dilution pressure balanced by TAO inflows

---

## TAO Tokenomics

| Parameter | Value |
|-----------|-------|
| Maximum supply | 21,000,000 TAO |
| Block time | 12 seconds |
| Pre-halving emission | 1 TAO/block (~7,200 TAO/day) |
| Post-halving emission | 0.5 TAO/block (~3,600 TAO/day) |
| First halving | December 14, 2025 (at 10.5M TAO mined) |
| Second halving | ~December 2029 |
| Halving trigger | Supply threshold, not fixed block |

TAO paid for subnet/neuron registration is recycled (removed from circulating supply, returned to unissued pool).

---

## Staking Under dTAO

### Programmatic Staking

```python
from bittensor.utils.balance import tao

subtensor.add_stake(wallet, netuid=1, hotkey_ss58="5D...", amount=tao(5.0))
subtensor.unstake(wallet, netuid=1, hotkey_ss58="5D...", amount=tao(1.0))
subtensor.move_stake(wallet, origin_netuid=1, origin_hotkey_ss58="5D...",
                     destination_netuid=1, destination_hotkey_ss58="5E...", amount=tao(1.0))
```

### Validator Stake Weight

```
effective_stake = alpha_stake + TAO_stake × tao_weight
```

Current `tao_weight` = 0.18 (gradually shifting to make alpha dominant).

### Delegation

- Any TAO holder can delegate to a validator (no hardware required)
- Minimum nominator stake: 0.1 TAO
- Validator take (commission): default 18%, configurable
- Nominator emission: `(nominator_stake / total_delegated) × (1 - take) × validator_emission`

---

## Implications for Bittensor Knowledge Network

### The 41/41/18 Split is Protocol-Enforced

Our emission model document describes custom pools (45% traversal, 30% quality, 15% topology, 10% reserve). Under dTAO, the actual distribution is:

| Recipient | Protocol Share | Our Control |
|-----------|---------------|-------------|
| Subnet Owner | 18% | Fixed by protocol — goes to our owner wallet |
| Miners | 41% | Distributed by Yuma Consensus based on **our weight assignments** |
| Validators + Stakers | 41% | Distributed by bond/dividend mechanism |

**Our "emission pools" must be implemented as weight-setting strategies**, not separate token flows. The weights we assign to miners determine how that 41% miner share is distributed among them.

### Subnet Economic Health

Our subnet's emission share depends on **net TAO staking inflows**. To attract stakers:
- Demonstrate consistent, valuable miner output
- Maintain healthy validator vtrust scores
- Build alpha token value through sustained inflows

### Owner Revenue

The 18% owner share is significant and automatic. This can fund:
- Development and maintenance
- The "proposal reserve" concept from our emission model
- Operational costs

### No Native Escrow

Bittensor has no built-in escrow. Our proposal bonds and traversal credits need either:
1. **EVM smart contracts** on Subtensor's EVM (recommended — see `evm-integration.md`)
2. **Off-chain validator-mediated settlement**

---

## Sources

- [Emission | Bittensor](https://docs.learnbittensor.org/learn/emissions)
- [Understanding Subnets](https://docs.learnbittensor.org/subnets/understanding-subnets)
- [Staking/Delegation Overview](https://docs.learnbittensor.org/staking-and-delegation/delegation)
- [Tokenomics](https://docs.taostats.io/docs/tokenomics)
- [Bittensor Halving](https://bittensorhalving.com/)
- [Coinbase Emission Implementation](https://docs.learnbittensor.org/navigating-subtensor/emissions-coinbase)
