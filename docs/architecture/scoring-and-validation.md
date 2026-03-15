# Scoring and Validation

## Overview

Validators evaluate miner quality across four dimensions — traversal accuracy, narrative quality, graph topology, and corpus integrity — then commit normalised weights to the Bittensor chain.

---

## Validator Class

The `Validator` class is the top-level runtime object. It holds:

- `wallet` — Bittensor wallet used for signing weight commits
- `subtensor` — chain interface for metagraph syncs and `set_weights` calls
- `metagraph` — current snapshot of registered UIDs and their metadata
- `graph_store` — local `GraphStore` instance used for topology scoring
- `embedder` — embedding model used to score traversal quality

---

## Epoch Loop

### `run_epoch()`

A single epoch executes in order:

1. Sync metagraph from subtensor
2. Run `ScoringLoop` across all active UIDs
3. Broadcast `WeightCommit` to peer validators
4. Call `subtensor.set_weights()` if quorum is met
5. Call `graph_store.decay_edges(EDGE_DECAY_RATE)` to age graph state

### `run_forever()`

Wraps `run_epoch()` in an infinite loop, sleeping `EPOCH_SLEEP_S` between epochs. Exceptions are caught and logged so a single failure does not halt the validator.

---

## ScoringLoop

`ScoringLoop` drives one full scoring epoch:

1. Iterate over all registered UIDs in the metagraph
2. Issue a `NarrativeHop` challenge to each miner
3. Issue a `CorpusChallenge` to each miner
4. Compute four sub-scores per UID
5. Normalise and combine into a final score

---

## Four Sub-Scores

All sub-scores are min-max normalised independently across the UID population before being combined.

### 1. Traversal Score

Measures how relevant the miner's returned chunks are to the query.

- Computed as cosine similarity between the returned chunks and the query embedding
- If the miner returns pre-computed scores, those are used directly
- Otherwise the validator re-embeds the returned chunks and computes similarity itself

**Latency penalty:**

Beyond `LATENCY_SOFT_LIMIT_S`, the score is penalised linearly:

```
penalty = min(latency_excess * LATENCY_PENALTY_PER_S, LATENCY_MAX_PENALTY)
final_traversal = raw_traversal * (1 - penalty)
```

### 2. Quality Score

A `NarrativeHop` challenge tests the miner's ability to produce coherent narrative transitions.

The validator synthesises a `(from_node, to_node)` pair and sends it to the miner. The returned narrative is scored by a word-count heuristic:

| Condition | Score |
|---|---|
| word count < `MIN_HOP_WORDS` | 0.2 |
| word count > `MAX_HOP_WORDS` | 0.6 |
| word count in range | 1.0 |

Future improvement: replace the word-count heuristic with embedding-based coherence scoring and groundedness checks against the miner's retrieved chunks.

### 3. Topology Score

Derived from the validator's local `graph_store`. For each miner UID, the score blends two signals:

```
topology = 0.6 * min(betweenness, 1.0)
         + 0.4 * min(log1p(edge_weight_sum) / log1p(50), 1.0)
```

- **Betweenness centrality** (60%) — computed via Brandes' algorithm (O(VE)), suitable for graphs up to approximately 500 nodes. Rewards miners whose nodes bridge distinct clusters.
- **Outgoing edge weight sum** (40%) — soft-capped via `log1p` to prevent a small number of heavy edges from dominating.

### 4. Corpus Score

A `CorpusChallenge` verifies Merkle root stability.

The validator re-queries the miner using the reserved key `__corpus_challenge__` and checks whether the returned `merkle_root` matches the root observed in a prior query. A stable root indicates the miner is serving a consistent, unchanged corpus.

---

## Score Combination

After normalisation, the four sub-scores are combined with configurable weights from `SubnetConfig`:

```
final = TRAVERSAL_WEIGHT * traversal
      + QUALITY_WEIGHT   * quality
      + TOPOLOGY_WEIGHT  * topology
      + CORPUS_WEIGHT    * corpus
```

The result is a mapping of `uid → final_score`.

---

## Weight Commit Flow

1. The validator builds a `WeightCommit` containing the epoch identifier, scored UIDs, and normalised weights.
2. The commit is hashed with SHA-256 over `(epoch, uids, weights)`.
3. The hash is broadcast to all peer validators whose `validator_trust` exceeds `VALIDATOR_TRUST_MIN`.
4. The validator waits for acknowledgements. If the fraction of acknowledgements meets or exceeds `COMMIT_QUORUM`, the commit proceeds.
5. On quorum: `subtensor.set_weights(netuid, wallet, uids, weights)` is called.
6. After a successful weight commit, `graph_store.decay_edges(EDGE_DECAY_RATE)` is applied.

---

## Configuration Reference

| Parameter | Description |
|---|---|
| `LATENCY_SOFT_LIMIT_S` | Seconds after which latency penalty begins |
| `LATENCY_PENALTY_PER_S` | Fractional penalty per excess second |
| `LATENCY_MAX_PENALTY` | Maximum fractional latency penalty (capped) |
| `MIN_HOP_WORDS` | Minimum word count for a full quality score |
| `MAX_HOP_WORDS` | Maximum word count before score is capped |
| `TRAVERSAL_WEIGHT` | Weight for traversal sub-score |
| `QUALITY_WEIGHT` | Weight for quality sub-score |
| `TOPOLOGY_WEIGHT` | Weight for topology sub-score |
| `CORPUS_WEIGHT` | Weight for corpus sub-score |
| `VALIDATOR_TRUST_MIN` | Minimum validator_trust to receive a WeightCommit broadcast |
| `COMMIT_QUORUM` | Required fraction of peer acknowledgements |
| `EDGE_DECAY_RATE` | Multiplier subtracted from edge weights each epoch |
| `EPOCH_SLEEP_S` | Seconds to sleep between epochs in `run_forever()` |
