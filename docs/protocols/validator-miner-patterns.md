# Validator & Miner Implementation Patterns

Production patterns derived from the Bittensor subnet template and successful subnet implementations.

---

## Project Structure (Subnet Template)

```
narrative-network/
├── neurons/
│   ├── miner.py              # Concrete miner (subclasses BaseMinerNeuron)
│   ├── validator.py           # Concrete validator (subclasses BaseValidatorNeuron)
│   └── gateway.py             # Gateway node (unique to our subnet)
├── narrative_network/
│   ├── __init__.py            # Version management
│   ├── protocol.py            # KnowledgeQuery, NarrativeHop synapse definitions
│   ├── forward.py             # Validator forward-pass logic
│   ├── reward.py              # Scoring functions (traversal, quality, topology, corpus)
│   └── base/
│       ├── neuron.py          # BaseNeuron (shared wallet/subtensor/metagraph)
│       ├── miner.py           # BaseMinerNeuron
│       └── validator.py       # BaseValidatorNeuron
├── min_compute.yml            # Hardware requirements
└── setup.py
```

---

## BaseNeuron Pattern

Shared initialization for both miners and validators:

```python
class BaseNeuron:
    def __init__(self, config):
        self.wallet = bt.Wallet(config=config)
        self.subtensor = bt.Subtensor(config=config)
        self.metagraph = self.subtensor.metagraph(config.netuid)
        self.uid = self.metagraph.hotkeys.index(self.wallet.hotkey.ss58_address)
        self.check_registered()

    def check_registered(self):
        if self.wallet.hotkey.ss58_address not in self.metagraph.hotkeys:
            bt.logging.error("Hotkey not registered. Exiting.")
            exit()

    def sync(self):
        self.check_registered()
        if self.should_sync_metagraph():
            self.resync_metagraph()
        if self.should_set_weights():
            self.set_weights()
        self.save_state()

    def should_sync_metagraph(self) -> bool:
        return (self.block - self.metagraph.last_update[self.uid]) > self.config.neuron.epoch_length
```

---

## Validator Patterns

### Main Loop

```python
def run(self):
    while True:
        self.loop.run_until_complete(self.concurrent_forward())
        if self.should_exit:
            break
        self.sync()       # metagraph + set_weights
        self.step += 1
```

### EMA Score Accumulation

```python
def update_scores(self, rewards: torch.FloatTensor, uids: list[int]):
    # Guard against NaN
    if torch.isnan(rewards).any():
        rewards = torch.nan_to_num(rewards, nan=0.0)

    # Scatter rewards onto full score array
    scattered = self.scores.scatter(0, torch.LongTensor(uids), rewards)

    # Exponential moving average
    alpha = self.config.neuron.moving_average_alpha  # typically 0.1
    self.scores = alpha * scattered + (1 - alpha) * self.scores
```

### Weight Setting

```python
def set_weights(self):
    # L1 normalize
    norm = torch.norm(self.scores, p=1)
    weights = self.scores / norm if norm != 0 else self.scores

    # Replace NaN
    weights = torch.nan_to_num(weights, nan=0.0)

    # Publish to chain
    self.subtensor.set_weights(
        wallet=self.wallet,
        netuid=self.config.netuid,
        uids=self.metagraph.uids,
        weights=weights,
        wait_for_inclusion=False,
    )
```

### Metagraph Resync with Hotkey Change Detection

Critical: reset scores when a new miner takes over a UID.

```python
def resync_metagraph(self):
    previous_hotkeys = self.hotkeys
    self.metagraph.sync(subtensor=self.subtensor)
    for uid, (old, new) in enumerate(zip(previous_hotkeys, self.metagraph.hotkeys)):
        if old != new:
            self.scores[uid] = 0   # reset for new miner
    self.hotkeys = copy(self.metagraph.hotkeys)
```

### Narrative Network Validator Specifics

Our validator has additional responsibilities beyond the template:

```python
class NarrativeValidator(BaseValidatorNeuron):
    def __init__(self, config):
        super().__init__(config)
        self.graph_store = KuzuGraphStore(config.graph_db_path)
        self.session_cache = RedisClient(config.redis_url)

    async def forward(self):
        """Per-epoch scoring loop."""
        # 1. Sample recently-completed sessions
        sessions = self.graph_store.sample_recent_sessions(n=self.config.sample_size)

        # 2. Replay NarrativeHop challenges
        for session in sessions:
            for hop in session.path:
                responses = await self.dendrite.forward(
                    axons=[self.metagraph.axons[uid] for uid in hop.destination_uids],
                    synapse=NarrativeHop(
                        destination_node_id=hop.node_id,
                        player_path=session.path_ids[:hop.index],
                        retrieved_chunks=hop.chunks,
                        session_id=f"challenge_{self.step}",
                    ),
                    timeout=30.0,
                    run_async=True,
                )
                scores = self.score_responses(responses, hop)
                self.update_scores(scores, hop.destination_uids)

        # 3. Run corpus challenges (Merkle integrity)
        await self.run_corpus_challenges()

        # 4. Compute topology scores
        self.update_topology_scores()

        # 5. Decay graph edges
        self.graph_store.decay_edges()

    def score_responses(self, responses, hop):
        """Four-axis comparative scoring."""
        traversal = self.score_traversal(responses, hop)     # 0.40 weight
        quality = self.score_quality(responses, hop)          # 0.35 weight
        topology = self.score_topology(responses, hop)        # 0.25 weight
        return 0.40 * traversal + 0.35 * quality + 0.25 * topology
```

---

## Miner Patterns

### Axon Setup and Handler Registration

```python
self.axon = bt.Axon(wallet=self.wallet, config=self.config)
self.axon.attach(
    forward_fn=self.forward,
    blacklist_fn=self.blacklist,
    priority_fn=self.priority,
)
```

### Main Loop

```python
def run(self):
    self.sync()
    self.axon.serve(netuid=self.config.netuid, subtensor=self.subtensor)
    self.axon.start()

    while True:
        self.sync()       # re-registration check + metagraph update
        self.step += 1
```

### Domain Miner (Knowledge Server)

```python
class DomainMiner(BaseMinerNeuron):
    def __init__(self, config):
        super().__init__(config)
        self.vector_store = ChromaStore(config.corpus_path)
        self.merkle_tree = MerkleTree(config.corpus_path)

    async def forward(self, synapse: KnowledgeQuery) -> KnowledgeQuery:
        if synapse.query_text == "__corpus_challenge__":
            # Return Merkle proof for integrity check
            synapse.merkle_proof = self.merkle_tree.get_proof()
            return synapse

        # Normal knowledge retrieval
        results = self.vector_store.query(
            embedding=synapse.query_embedding,
            text=synapse.query_text,
            top_k=synapse.top_k,
        )
        synapse.chunks = results.chunks
        synapse.domain_similarity = results.similarity
        synapse.node_id = self.config.node_id
        synapse.agent_uid = self.uid
        return synapse
```

### Narrative Miner (Passage Generator)

```python
class NarrativeMiner(BaseMinerNeuron):
    def __init__(self, config):
        super().__init__(config)
        self.model = load_language_model(config.model_name)
        self.persona = load_persona(config.persona_path)

    async def forward(self, synapse: NarrativeHop) -> NarrativeHop:
        # Build prompt from context
        prompt = self.build_prompt(
            node_id=synapse.destination_node_id,
            path=synapse.player_path,
            prior=synapse.prior_narrative,
            chunks=synapse.retrieved_chunks,
            integration_notice=synapse.integration_notice,
        )

        # Generate passage
        passage = self.model.generate(prompt, max_tokens=400, persona=self.persona)

        # Generate choice cards (adjacent nodes)
        choices = self.generate_choices(synapse.destination_node_id, passage)

        synapse.narrative_passage = passage
        synapse.choice_cards = choices
        synapse.passage_embedding = self.embed(passage)
        synapse.agent_uid = self.uid
        return synapse
```

---

## Security Patterns

### Always Implement Blacklisting

```python
async def blacklist(self, synapse) -> tuple[bool, str]:
    if synapse.dendrite.hotkey not in self.metagraph.hotkeys:
        return True, "Hotkey not registered"
    uid = self.metagraph.hotkeys.index(synapse.dendrite.hotkey)
    if self.config.blacklist.force_validator_permit:
        if not self.metagraph.validator_permit[uid]:
            return True, "No validator permit"
    return False, "Allowed"
```

### Score Array Resizing

Handle metagraph growth (new miners registering):

```python
def resync_metagraph(self):
    self.metagraph.sync(subtensor=self.subtensor)
    if len(self.metagraph.hotkeys) > len(self.scores):
        new_scores = torch.zeros(len(self.metagraph.hotkeys))
        new_scores[:len(self.scores)] = self.scores
        self.scores = new_scores
```

### NaN Guard on Every Score Update

```python
rewards = torch.nan_to_num(rewards, nan=0.0)
weights = torch.nan_to_num(weights, nan=0.0)
```

---

## Deployment

### Recommended Stack

```
Docker container (pinned image per release)
  └── validator/miner process
  └── volume mount for state persistence

Auto-upgrader service
  └── polls GitHub releases
  └── configurable delay before pulling (e.g., 15 min)
  └── restarts container after upgrade

Watchdog service
  └── monitors "blocks since last set weight"
  └── auto-restarts on stall detection
```

### Hardware Minimums

| Component | CPU | RAM | GPU | Notes |
|-----------|-----|-----|-----|-------|
| Gateway | 2-4 vCPU | 8 GB | No | Only internet-facing |
| Domain Miner | 2 vCPU | 4 GB | No | One per node ID |
| Narrative Miner | 4 vCPU | 16 GB | Optional (improves quality) | Competes at each node |
| Validator | 8 vCPU | 32 GB | No | Runs scoring + graph store |

### Testing Progression

1. **Local devnet** (250ms blocks):
   ```bash
   docker run ghcr.io/opentensor/subtensor-localnet:devnet-ready \
     --dev --sealing=interval --block-time=250
   ```
2. **Testnet** (finney testnet)
3. **Mainnet**

---

## Common Anti-Patterns to Avoid

| Anti-Pattern | Impact | Fix |
|--------------|--------|-----|
| No blacklist validation | Wastes compute on unauthorized requests | Implement `blacklist_fn` |
| Not resetting scores on hotkey churn | New miner inherits old score | Zero scores in `resync_metagraph()` |
| NaN propagation | Undefined weights | `nan_to_num` before every `set_weights()` |
| Not handling metagraph growth | Index errors | Resize score arrays |
| Publishing axon on validators | Unnecessary attack surface | Disable axon on validators |
| Hardcoded miner responses | Detected by fuzzy/persona-based scoring | Use real computation |
| No state persistence | Lost scores on restart | Save/load `state.npz` |

---

## Sources

- [Subnet Template](https://github.com/opentensor/bittensor-subnet-template)
- [Validating in Bittensor](https://docs.learnbittensor.org/validators)
- [Mining in Bittensor](https://docs.learnbittensor.org/miners)
- [Secure & Performant Bittensor Validation](https://blog.unit410.com/engineering/bittensor/security/monitoring/2024/08/14/secure-performant-bittensor-validation.html)
- [Incentive Mechanisms](https://docs.learnbittensor.org/learn/anatomy-of-incentive-mechanism)
