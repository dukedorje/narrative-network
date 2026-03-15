# Bittensor SDK v10 Reference

**Package:** `bittensor` (PyPI)
**Version:** 10.1.0 (stable, Jan 2026)
**Python:** >=3.10, <3.15
**Docs:** https://docs.learnbittensor.org/

## Installation

```bash
pip install bittensor           # base
pip install bittensor[torch]    # with PyTorch support
pip install bittensor[dev]      # development tools
```

Companion packages:
- `bittensor-wallet` — standalone wallet SDK
- `bittensor-cli` — btcli command-line tool

## v10 Breaking Changes (Migration from v9)

SDK v10 is a **major breaking release**. Key changes:

### 1. PascalCase Imports Required

```python
# BEFORE (v9): from bittensor import subtensor, wallet, axon
# AFTER (v10):
from bittensor import Subtensor, Wallet, Axon, Dendrite, Synapse
```

### 2. Balance Objects Required (No Raw Floats)

```python
from bittensor.utils.balance import tao, rao

# tao(1.0) == 1 TAO == 1_000_000_000 RAO
subtensor.add_stake(wallet, netuid=1, hotkey_ss58="5D...", amount=tao(5.0))
```

New exceptions: `BalanceTypeError`, `BalanceUnitMismatchError`

### 3. ExtrinsicResponse Return Type (Not bool)

```python
response = subtensor.transfer(wallet, destination_ss58="5D...", amount=tao(1.0))
response.success            # bool
response.message            # str
response.extrinsic_fee      # network fee
response.transaction_tao_fee
response.transaction_alpha_fee
response.data               # dict (e.g. {"uid": 42})
response.error              # Python exception or None
response.extrinsic_receipt.block_number
```

### 4. Parameter Renames

| Old | New |
|-----|-----|
| `hotkey` | `hotkey_ss58` |
| `coldkey` | `coldkey_ss58` |
| `dest` | `destination_ss58` |
| `block_number` / `block_id` | `block` |
| `safe_staking` | `safe_unstaking` |
| `max_retries` | `max_attempts` |

### 5. Method Renames

| Old | New |
|-----|-----|
| `commit()` | `set_commitment()` |
| `get_subnets()` | `get_all_subnets_netuid()` |
| `increase_take()` / `decrease_take()` | `set_delegate_take()` |
| `get_stake_for_coldkey()` | `get_stake_info_for_coldkey()` |

### 6. New `mechid` Parameter

Subnets can run up to 2 independent incentive mechanisms. `mechid=0` is default.

### 7. Environment Variable Renames

| Old | New |
|-----|-----|
| `BT_CHAIN_ENDPOINT` | `BT_SUBTENSOR_CHAIN_ENDPOINT` |
| `BT_NETWORK` | `BT_SUBTENSOR_NETWORK` |

---

## Core Modules

| Module | Purpose |
|--------|---------|
| `bittensor.core.subtensor` | Sync blockchain client |
| `bittensor.core.async_subtensor` | Async blockchain client |
| `bittensor.core.synapse` | Synapse data protocol |
| `bittensor.core.axon` | Miner server |
| `bittensor.core.dendrite` | Validator client |
| `bittensor.core.metagraph` | Subnet state snapshot |
| `bittensor.core.extrinsics` | Transaction primitives |
| `bittensor.utils.balance` | `Balance`, `tao()`, `rao()` |

---

## Subtensor Client

### Connection

```python
from bittensor import Subtensor

subtensor = Subtensor()                              # mainnet (finney)
subtensor = Subtensor(network="test")                # testnet
subtensor = Subtensor(network="local")               # local devnet
subtensor = Subtensor(network="ws://127.0.0.1:9944") # custom endpoint

# Async
from bittensor.core.async_subtensor import AsyncSubtensor
async with AsyncSubtensor(network="finney") as subtensor:
    block = await subtensor.block
```

### Weight Setting

```python
# Direct set (if subnet permits)
response = subtensor.set_weights(
    wallet, netuid=1, uids=[0, 1, 2], weights=[0.5, 0.3, 0.2], mechid=0
)

# Commit-reveal (manual path)
response = subtensor.commit_weights(
    wallet, netuid=1, salt=[1, 2, 3, 4],
    uids=[0, 1, 2], weights=[0.5, 0.3, 0.2], mechid=0
)
response = subtensor.reveal_weights(
    wallet, netuid=1, uids=[0, 1, 2], weights=[0.5, 0.3, 0.2], salt=[1, 2, 3, 4]
)
```

Note: With commit-reveal v4 (Drand), validators just call `set_weights()` — the chain handles encryption/reveal automatically.

### Transfers and Staking

```python
from bittensor.utils.balance import tao

# Transfer
response = subtensor.transfer(wallet, destination_ss58="5D...", amount=tao(1.0))

# Stake
subtensor.add_stake(wallet, netuid=1, hotkey_ss58="5D...", amount=tao(5.0))
subtensor.unstake(wallet, netuid=1, hotkey_ss58="5D...", amount=tao(1.0))
subtensor.move_stake(wallet, origin_netuid=1, origin_hotkey_ss58="5D...",
                     destination_netuid=1, destination_hotkey_ss58="5E...", amount=tao(1.0))
```

### Registration

```python
subtensor.burned_register(wallet, netuid=1)   # burn TAO to register
subtensor.register(wallet, netuid=1)           # PoW registration
```

### On-Chain Metadata

```python
response = subtensor.set_commitment(wallet, netuid=1, data="my_metadata_string")
```

### Queries

```python
balance = subtensor.get_balance("5D...")
neuron = subtensor.get_neuron_for_pubkey_and_subnet(pubkey, netuid=1)
block_num = subtensor.block
metagraph = subtensor.metagraph(netuid=1)
```

All extrinsic methods support: `mev_protection`, `wait_for_inclusion`, `wait_for_finalization`, `raise_error`

---

## Wallet

```python
from bittensor import Wallet

wallet = Wallet(name="my_wallet", hotkey="my_hotkey", path="~/.bittensor/wallets/")

wallet.coldkey       # Keypair (decrypts on access)
wallet.hotkey        # Keypair (usually unencrypted)
wallet.coldkeypub    # Public key only

wallet.create_if_non_existent()
wallet.new_coldkey(n_words=12, use_password=True)
wallet.new_hotkey(n_words=12, use_password=False)

# Dev/test
wallet.create_coldkey_from_uri("//Alice")
wallet.create_hotkey_from_uri("//Bob")
```

**Auth model:**
- **Miners**: hotkey signs axon responses
- **Validators**: hotkey signs weight submissions and dendrite requests
- **Financial ops** (transfer, stake, subnet management): coldkey required
- One coldkey → many hotkeys; one hotkey per subnet UID

---

## Metagraph

```python
from bittensor.core.metagraph import Metagraph

metagraph = Metagraph(netuid=1, network="finney", sync=True)         # lite mode
metagraph = Metagraph(netuid=1, network="finney", lite=False, sync=True)  # full (W + B matrices)
```

### Key Fields

| Attribute | Description |
|-----------|-------------|
| `n` | Total registered neurons |
| `block` | Block number at sync time |
| `uids` | Unique neuron IDs (tensor) |
| `hotkeys` | Hotkey SS58 addresses (list) |
| `coldkeys` | Coldkey SS58 addresses (list) |
| `axons` | `AxonInfo` objects (IP/port/version) |
| `S` | Total stake (tensor) |
| `AS` | Alpha stake per neuron |
| `TS` | TAO stake per neuron |
| `R` | Ranks (post-consensus clipping) |
| `T` | Trust (consensus alignment ratio) |
| `Tv` | Validator trust |
| `C` | Consensus (stake-weighted median) |
| `I` | Incentive (miner rewards) |
| `E` | Emission in RAO/block |
| `D` | Dividends (validator bond rewards) |
| `W` | Weights matrix (lite=False only) |
| `B` | Bonds matrix (lite=False only) |
| `validator_permit` | Validator permission flags |
| `last_update` | Blocks since last weight update |

```python
metagraph.sync()    # refresh to latest block
metagraph.save()    # cache to disk
metagraph.load()    # restore from cache
```

Does not auto-refresh — call `.sync()` every tempo (~360 blocks / ~72 min).

---

## Logging

```python
import bittensor as bt

bt.logging.set_debug(True)
bt.logging.set_trace(True)    # most verbose
bt.logging.set_info(True)     # default
```

Environment variables:
```bash
BT_LOGGING_DEBUG=1
BT_LOGGING_TRACE=1
BT_LOGGING_RECORD_LOG=1
BT_LOGGING_LOGGING_DIR=/path/to/logs
```

---

## Key Environment Variables

```bash
BT_SUBTENSOR_NETWORK=finney
BT_SUBTENSOR_CHAIN_ENDPOINT=ws://127.0.0.1:9944
BT_AXON_PORT=8091
BT_AXON_MAX_WORKERS=10
BT_MEV_PROTECTION=1
BT_WALLET_NAME=my_wallet
BT_WALLET_HOTKEY=my_hotkey
USE_TORCH=1
```

---

## Sources

- [Install Bittensor SDK](https://docs.learnbittensor.org/getting-started/installation)
- [SDK v10 Migration Guide](https://docs.learnbittensor.org/sdk/migration-guide)
- [Subtensor API Docs](https://docs.learnbittensor.org/sdk/subtensor-api)
- [Python API Reference](https://docs.learnbittensor.org/python-api/html/autoapi/bittensor/core/subtensor/)
- [Environment Variables](https://docs.learnbittensor.org/sdk/env-vars)
- [PyPI — bittensor](https://pypi.org/project/bittensor/)
