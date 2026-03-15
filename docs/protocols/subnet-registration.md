# Subnet Registration and Configuration

## Creating a Subnet

```bash
# Check current burn cost
btcli subnet burn-cost --network finney   # mainnet
btcli subnet burn-cost --network test     # testnet

# Create subnet
btcli subnet create --network test        # testnet
btcli subnet create                       # mainnet

# New subnets are INACTIVE by default — must be started:
btcli subnet start --netuid <your_netuid>
```

### Cost Mechanics

- **Dynamic burn cost**: decreases gradually over time, **doubles** every time any new subnet is created
- Burned TAO is destroyed (sunk cost, non-recoverable)
- Rate limit: one subnet creation per **28,800 blocks** (~4 days) network-wide
- Network hard cap: **128 active subnets**
- If at cap: creating a new one deregisters the lowest-EMA-priced non-immune subnet
- New subnets have a **7-day activation delay** before running epochs
- New subnets have a **4-month immunity period** from deregistration

---

## Subnet Hyperparameters

Set via `btcli sudo set` (requires the coldkey that created the subnet).

### Owner-Configurable Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ImmunityPeriod` | 5000 blocks (~16.7h) | New neurons protected from deregistration |
| `MaxAllowedUids` | 256 | Max neurons on subnet |
| `WeightsVersion` | 0 | Version protection for weight updates |
| `CommitRevealWeightsEnabled` | False | Prevents weight-copying |
| `CommitRevealPeriod` | 1 | Tempos before weights are revealed |
| `MinAllowedWeights` | 1 | Min weights validators must set |
| `MaxWeightLimit` | 65535 | Upper bound on weight connections |
| `ActivityCutoff` | 5000 blocks | Min activity to remain active |
| `ServingRateLimit` | 50 | Rate limit for miner axon calls |
| `BondsMovingAverage` | varies | Moving avg window for bonds |
| `LiquidAlphaEnabled` | False | Dynamic consensus-based bond alpha |
| `MinBurn` / `MaxBurn` | 0.0005τ / 100τ | Bounds on neuron registration burn |

### Root-Only Parameters (Not Owner-Settable)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `Tempo` | 360 blocks (~72 min) | Blocks per epoch; fixed |
| `MaxAllowedValidators` | 64 | Max validators per subnet |
| `MaxRegistrationsPerBlock` | 1 | Registration throughput cap |
| `WeightsRateLimit` | 100 blocks (~20 min) | Min blocks between weight commits |
| `Kappa` | 0.5 (32767 u16) | Consensus majority ratio |

---

## Miner & Validator Registration

Both use the same command:

```bash
btcli subnet register \
  --netuid <target_netuid> \
  --wallet.name <coldkey_name> \
  --wallet.hotkey <hotkey_name>
```

- Dynamic burn cost (sunk, non-recoverable)
- Each hotkey: one UID per subnet, can hold UIDs on multiple subnets

### Validator Requirements (Post-Registration)

To obtain a **validator permit** and set weights:
1. Registered UID on the subnet
2. Stake weight ≥ 1000: `α + (0.18 × τ)` where α = alpha stake, τ = TAO stake
3. Be in the **top 64 nodes by emissions**

```bash
btcli stake add --wallet.name <name> --wallet.hotkey <hotkey>
```

Permits recalculated every epoch. Falling below thresholds loses permit but doesn't auto-deregister.

---

## Deregistration

### Neuron-Level (Miner/Validator from Subnet)

- After `ImmunityPeriod` expires AND subnet is at `MaxAllowedUids` AND a new registration arrives:
  - Lowest-performing (by emissions) non-immune neuron is deregistered
- Subnet owner hotkey has **permanent immunity**

### Subnet-Level

- Triggered when 128-subnet cap reached + new subnet attempts to register
- Lowest **EMA price** subnet (outside 4-month immunity) is deregistered
- Rate limit: at most once every 2 days (14,400 blocks)
- On deregistration: all alpha tokens swapped back to TAO and distributed to holders

---

## Subnet Owner Responsibilities

- Pay the burn cost at creation
- Start the subnet after creation
- Set hyperparameters via `btcli sudo set`
- Maintain a validator (must meet top-64 / 1000+ stake requirements)
- Receive **18% of alpha emissions** each tempo automatically
- Owner coldkey is the only key that can change hyperparameters

---

## Recommended Configuration for Narrative Network

Based on our architecture:

```
CommitRevealWeightsEnabled = True      # prevent weight copying
CommitRevealPeriod = 1                 # 1 tempo delay
ImmunityPeriod = 7200                  # ~24h for incubation phase
MaxAllowedUids = 256                   # room for growth
MinAllowedWeights = 8                  # validators must score enough miners
WeightsVersion = 1                     # version-gate weight updates
LiquidAlphaEnabled = True              # reward early miner discovery
```

---

## Testing Progression

1. **Local devnet** — fast-block mode (250ms/block):
   ```bash
   docker run ghcr.io/opentensor/subtensor-localnet:devnet-ready \
     --dev --sealing=interval --block-time=250
   ```
2. **Testnet** (`finney` testnet)
3. **Mainnet**

---

## Sources

- [Create a Subnet](https://docs.learnbittensor.org/subnets/create-a-subnet)
- [Subnet Hyperparameters](https://docs.learnbittensor.org/subnets/subnet-hyperparameters)
- [Subnet Deregistration](https://docs.learnbittensor.org/subnets/subnet-deregistration)
- [Subnet Creator's Guide](https://docs.learnbittensor.org/subnets/subnet-creators-btcli-guide)
- [Validating in Bittensor](https://docs.learnbittensor.org/validators)
- [Mining in Bittensor](https://docs.learnbittensor.org/miners)
