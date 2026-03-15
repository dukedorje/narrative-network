# Scoring and Validation

## Overview

Validators evaluate miner quality across four dimensions — traversal accuracy, narrative quality, graph topology, and corpus integrity — then set normalised weights on the Bittensor chain. Yuma Consensus aggregates weights from all validators to determine miner emission.

---

## Validator Class

The `Validator` class is the top-level runtime object. It holds:

- `wallet` — `bt.Wallet` used for signing weight commits (SDK v10: PascalCase)
- `subtensor` — `bt.Subtensor` chain interface for metagraph syncs and `set_weights` calls
- `metagraph` — current snapshot of registered UIDs and their metadata
- `graph_store` — local `GraphStore` instance used for topology scoring
- `embedder` — embedding model used to score traversal quality
- `scores` — EMA-accumulated score tensor, one entry per UID

---

## Epoch Loop

### `run_epoch()`

A single epoch executes in order:

1. Sync metagraph from subtensor (detect hotkey changes, resize score array)
2. Run `ScoringLoop` across all active UIDs
3. Normalize scores and call `subtensor.set_weights()` (SDK v10 API)
4. Call `graph_store.decay_edges(EDGE_DECAY_RATE)` to age graph state

### `run_forever()`

Wraps `run_epoch()` in an infinite loop, sleeping `EPOCH_SLEEP_S` between epochs. Exceptions are caught and logged so a single failure does not halt the validator.

### Weight Setting (Yuma Consensus, No Custom Quorum)

Each validator independently sets weights. **There is no custom BFT quorum.** Yuma Consensus provides Byzantine fault tolerance at the protocol level:

- Each validator calls `set_weights()` independently after scoring
- Yuma Consensus clips outlier weights via κ-majority threshold (50% stake)
- Bond penalty punishes validators who deviate from consensus
- Commit-reveal v4 (Drand time-lock encryption) prevents weight copying automatically

```python
def set_weights(self):
    from bittensor.utils.balance import tao

    # L1 normalize
    norm = torch.norm(self.scores, p=1)
    weights = self.scores / norm if norm != 0 else self.scores

    # Guard against NaN
    weights = torch.nan_to_num(weights, nan=0.0)

    # Publish to chain (SDK v10 API)
    response = self.subtensor.set_weights(
        wallet=self.wallet,
        netuid=self.config.netuid,
        uids=self.metagraph.uids,
        weights=weights,
        mechid=0,                    # primary scoring mechanism
        wait_for_inclusion=False,    # non-blocking
    )
    if not response.success:
        bt.logging.error(f"set_weights failed: {response.message}")
```

With `CommitRevealWeightsEnabled = True` on our subnet, the chain automatically encrypts weights via Drand and reveals them after `CommitRevealPeriod` tempos. No manual commit/reveal steps needed.

---

## Metagraph Resync

Critical: detect hotkey changes and resize score arrays.

```python
def resync_metagraph(self):
    previous_hotkeys = copy(self.hotkeys)
    self.metagraph.sync(subtensor=self.subtensor)

    # Resize score array if metagraph grew
    if len(self.metagraph.hotkeys) > len(self.scores):
        new_scores = torch.zeros(len(self.metagraph.hotkeys))
        new_scores[:len(self.scores)] = self.scores
        self.scores = new_scores

    # Reset scores for UIDs where the hotkey changed (new miner at that slot)
    for uid, (old, new) in enumerate(zip(previous_hotkeys, self.metagraph.hotkeys)):
        if old != new:
            self.scores[uid] = 0

    self.hotkeys = copy(self.metagraph.hotkeys)
```

---

## ScoringLoop

`ScoringLoop` drives one full scoring epoch:

1. Iterate over all registered UIDs in the metagraph
2. Issue a `NarrativeHop` challenge to each miner
3. Issue a corpus challenge to each domain miner
4. Compute four sub-scores per UID
5. EMA-accumulate into the running score tensor

### EMA Score Accumulation

```python
def update_scores(self, rewards: torch.FloatTensor, uids: list[int]):
    if torch.isnan(rewards).any():
        rewards = torch.nan_to_num(rewards, nan=0.0)

    scattered = self.scores.scatter(0, torch.LongTensor(uids), rewards)

    alpha = self.config.neuron.moving_average_alpha  # typically 0.1
    self.scores = alpha * scattered + (1 - alpha) * self.scores
```

---

## Four Sub-Scores

All sub-scores are min-max normalised independently across the UID population before being combined.

### 1. Traversal Score (weight: 0.40)

Measures how relevant the miner's returned chunks are to the query.

- Computed as cosine similarity between the returned chunks and the query embedding
- If the miner returns pre-computed scores, those are cross-checked by the validator
- Otherwise the validator re-embeds the returned chunks and computes similarity itself

**Latency penalty:**

Beyond `LATENCY_SOFT_LIMIT_S`, the score is penalised linearly:

```
penalty = min(latency_excess * LATENCY_PENALTY_PER_S, LATENCY_MAX_PENALTY)
final_traversal = raw_traversal * (1 - penalty)
```

### 2. Quality Score (weight: 0.30)

A `NarrativeHop` challenge tests the miner's ability to produce coherent narrative transitions.

The validator synthesises a `(from_node, to_node)` pair and sends it to the miner. The returned narrative is scored on:

- **Path coherence** (40%): cosine similarity with running path embedding mean
- **Directional progress** (30%): movement toward destination centroid
- **Length heuristic** (30%, MVP): word count in target range

| Condition | Length Score |
|---|---|
| word count < `MIN_HOP_WORDS` | 0.2 |
| word count > `MAX_HOP_WORDS` | 0.6 |
| word count in range | 1.0 |

Future improvement: replace the length heuristic with embedding-based coherence and groundedness checks.

### 3. Topology Score (weight: 0.15)

Derived from the validator's local `graph_store`. For each miner UID, the score blends two signals:

```
topology = 0.6 * min(betweenness, 1.0)
         + 0.4 * min(log1p(edge_weight_sum) / log1p(50), 1.0)
```

- **Betweenness centrality** (60%) — computed via Brandes' algorithm (O(VE)), suitable for graphs up to approximately 500 nodes. Rewards miners whose nodes bridge distinct clusters.
- **Outgoing edge weight sum** (40%) — soft-capped via `log1p` to prevent a small number of heavy edges from dominating.

### 4. Corpus Score (weight: 0.15)

A corpus challenge verifies Merkle root stability.

The validator re-queries the miner using the reserved key `__corpus_challenge__` and checks whether the returned Merkle proof matches the root stored on-chain via `set_commitment()`. A stable root indicates the miner is serving a consistent, unchanged corpus.

**Penalty:** Miners that fail corpus challenges receive a corpus score of 0.0, which heavily drags down their combined weight → zero emission → eventual deregistration. This replaces native slashing (which Bittensor does not support).

---

## Score Combination

After normalisation, the four sub-scores are combined with configurable weights:

```
final = TRAVERSAL_WEIGHT * traversal      # 0.40
      + QUALITY_WEIGHT   * quality         # 0.30
      + TOPOLOGY_WEIGHT  * topology        # 0.15
      + CORPUS_WEIGHT    * corpus          # 0.15
```

The result is a mapping of `uid → final_score` that becomes the weight vector for `set_weights()`.

---

## Comparative Attestation

Multiple miners respond to the same `NarrativeHop` call. The validator does not score each miner in isolation against ground truth — there is none. Instead it ranks them comparatively: "miner A's passage was more grounded, coherent, and edge-useful than miner B's, relative to this session's path and this node's attractor."

The comparative ranking, accumulated across epochs via EMA and aggregated across validators via Yuma Consensus, is the fundamental unit of value the network produces.

---

## How Yuma Consensus Enforces Honest Scoring

Scoring honesty is enforced by the protocol, not by a custom quorum:

1. **κ-majority clipping**: Any validator weight that exceeds what 50% of stake supports gets clipped. A minority cabal setting inflated weights sees those weights reduced.
2. **Bond penalty**: Out-of-consensus validators earn lower bond shares → lower dividends. Consistently deviating validators lose influence and income.
3. **Commit-reveal**: Weights are encrypted for 1+ tempos via Drand. Copiers only see stale weights, which produces vtrust penalties when miner rankings change.
4. **vtrust**: Sum of consensus-clipped weights. Validators with high vtrust earn proportionally more. Honest scoring → high vtrust → maximum earnings.

No custom BFT quorum is needed. Yuma Consensus provides stronger guarantees with less implementation complexity.

---

## Configuration Reference

| Parameter | Description |
|---|---|
| `LATENCY_SOFT_LIMIT_S` | Seconds after which latency penalty begins |
| `LATENCY_PENALTY_PER_S` | Fractional penalty per excess second |
| `LATENCY_MAX_PENALTY` | Maximum fractional latency penalty (capped) |
| `MIN_HOP_WORDS` | Minimum word count for a full quality score |
| `MAX_HOP_WORDS` | Maximum word count before score is capped |
| `TRAVERSAL_WEIGHT` | Weight for traversal sub-score (0.40) |
| `QUALITY_WEIGHT` | Weight for quality sub-score (0.30) |
| `TOPOLOGY_WEIGHT` | Weight for topology sub-score (0.15) |
| `CORPUS_WEIGHT` | Weight for corpus sub-score (0.15) |
| `EDGE_DECAY_RATE` | Multiplier subtracted from edge weights each epoch |
| `EPOCH_SLEEP_S` | Seconds to sleep between epochs in `run_forever()` |
