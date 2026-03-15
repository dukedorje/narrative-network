# Synapse Implementation Guide

## Synapse Protocol Basics

All validator-miner communication in Bittensor uses `bt.Synapse` subclasses — Pydantic `BaseModel` objects transported over HTTP between Axon (miner) and Dendrite (validator).

```python
import bittensor as bt
import typing

class MyProtocol(bt.Synapse):
    # Input field (set by validator, read by miner)
    prompt: str = ""
    # Output field (filled by miner, read by validator)
    response: typing.Optional[str] = None
    # Required for body integrity verification
    required_hash_fields: tuple[str, ...] = ("prompt",)

    def deserialize(self) -> str:
        return self.response
```

### Built-In Synapse Fields

| Field | Type | Purpose |
|-------|------|---------|
| `name` | str | HTTP route identifier |
| `timeout` | float | Max query duration (seconds) |
| `total_size` | int | Request body size |
| `dendrite` | TerminalInfo | Sender metadata |
| `axon` | TerminalInfo | Receiver metadata |
| `computed_body_hash` | str | SHA3-256 integrity hash |

**TerminalInfo** contains: `status_code`, `status_message`, `process_time`, `ip`, `port`, `hotkey`, `signature`, `nonce`, `uuid`, `version`

**Status properties:** `is_success`, `is_failure`, `is_timeout`, `is_blacklist`, `failed_verification`

---

## Narrative Network Synapses

### KnowledgeQuery

```python
class KnowledgeQuery(bt.Synapse):
    """Gateway → Domain Miners: Retrieve relevant knowledge chunks."""

    # Request fields (set by gateway/validator)
    query_embedding: list[float] = []
    query_text: str = ""
    top_k: int = 5
    session_id: str = ""
    spec_version: int = 1

    # Response fields (set by miner)
    chunks: typing.Optional[list[dict]] = None        # [{text, embedding, score}]
    domain_similarity: typing.Optional[float] = None
    node_id: typing.Optional[str] = None
    agent_uid: typing.Optional[int] = None
    merkle_proof: typing.Optional[dict] = None         # corpus integrity proof

    required_hash_fields: tuple[str, ...] = ("query_embedding", "query_text", "session_id")

    def deserialize(self) -> dict:
        return {
            "chunks": self.chunks,
            "domain_similarity": self.domain_similarity,
            "node_id": self.node_id,
            "merkle_proof": self.merkle_proof,
        }
```

### NarrativeHop

```python
class NarrativeHop(bt.Synapse):
    """Gateway → Narrative Miners: Generate a narrative passage at a node."""

    # Request fields
    destination_node_id: str = ""
    player_path: list[str] = []
    path_embeddings: list[list[float]] = []
    prior_narrative: str = ""
    retrieved_chunks: list[dict] = []
    session_id: str = ""
    integration_notice: typing.Optional[dict] = None   # for bridge window foreshadowing

    # Response fields
    narrative_passage: typing.Optional[str] = None      # 200-400 tokens
    choice_cards: typing.Optional[list[dict]] = None    # [{node_id, label, teaser}]
    knowledge_synthesis: typing.Optional[str] = None
    passage_embedding: typing.Optional[list[float]] = None
    agent_uid: typing.Optional[int] = None

    required_hash_fields: tuple[str, ...] = (
        "destination_node_id", "player_path", "session_id"
    )

    def deserialize(self) -> dict:
        return {
            "narrative_passage": self.narrative_passage,
            "choice_cards": self.choice_cards,
            "knowledge_synthesis": self.knowledge_synthesis,
            "passage_embedding": self.passage_embedding,
        }
```

### Streaming Variant

For real-time narrative delivery, use `bt.StreamingSynapse`:

```python
class NarrativeHopStream(bt.StreamingSynapse):
    """Streaming variant for real-time passage delivery."""
    destination_node_id: str = ""
    player_path: list[str] = []
    # ... same fields as NarrativeHop ...

    async def process_streaming_response(self, response):
        async for chunk in response.content.iter_any():
            yield chunk.decode("utf-8")
```

---

## Axon Setup (Miner Side)

```python
import bittensor as bt

axon = bt.Axon(wallet=wallet, port=8091)

# Register handlers
axon.attach(
    forward_fn=handle_knowledge_query,
    blacklist_fn=blacklist_knowledge_query,
    priority_fn=priority_knowledge_query,
)
axon.attach(
    forward_fn=handle_narrative_hop,
    blacklist_fn=blacklist_narrative_hop,
    priority_fn=priority_narrative_hop,
)

axon.serve(netuid=NETUID, subtensor=subtensor)
axon.start()
```

### Blacklist Function (Security Gate)

Runs before deserialization — rejects unregistered/unauthorized requests:

```python
async def blacklist_knowledge_query(synapse: KnowledgeQuery) -> tuple[bool, str]:
    # Reject unregistered hotkeys
    if synapse.dendrite.hotkey not in metagraph.hotkeys:
        return True, "Hotkey not registered"
    # Optionally require validator permit
    uid = metagraph.hotkeys.index(synapse.dendrite.hotkey)
    if not metagraph.validator_permit[uid]:
        return True, "No validator permit"
    return False, "Allowed"
```

### Priority Function (Stake-Based Ordering)

```python
async def priority_knowledge_query(synapse: KnowledgeQuery) -> float:
    uid = metagraph.hotkeys.index(synapse.dendrite.hotkey)
    return float(metagraph.S[uid])  # higher stake = higher priority
```

---

## Dendrite Usage (Validator/Gateway Side)

```python
dendrite = bt.Dendrite(wallet=wallet)

# Query single miner
response = await dendrite.forward(
    axons=metagraph.axons[uid],
    synapse=KnowledgeQuery(query_text="quantum physics", query_embedding=embedding, top_k=5),
    timeout=12.0
)

# Query multiple miners in parallel
responses: list[NarrativeHop] = await dendrite.forward(
    axons=[metagraph.axons[uid] for uid in destination_uids],
    synapse=NarrativeHop(
        destination_node_id=node_id,
        player_path=path,
        retrieved_chunks=chunks,
        session_id=session_id,
    ),
    timeout=30.0,
    run_async=True   # parallel execution
)
```

### Checking Response Status

```python
for response in responses:
    if response.is_success:
        passage = response.deserialize()
    elif response.is_timeout:
        bt.logging.warning(f"Miner {response.axon.hotkey} timed out")
    elif response.is_blacklist:
        bt.logging.warning(f"Blacklisted by miner")
```

---

## Corpus Challenge Synapse

Validators use `KnowledgeQuery` with a special query for Merkle integrity checks:

```python
challenge = KnowledgeQuery(
    query_text="__corpus_challenge__",
    query_embedding=[],  # not needed for challenge
    top_k=1,
    session_id=f"challenge_{epoch}",
)
response = await dendrite.forward(axons=metagraph.axons[uid], synapse=challenge, timeout=10.0)
# Compare response.merkle_proof against committed Merkle root
```

---

## Design Considerations

### Synapse Size Limits

- Synapse fields are serialized to HTTP headers and body
- Large embeddings (768-dim float lists) should go in the body via `required_hash_fields`
- Keep response payloads reasonable — narrative passages of 200-400 tokens are fine
- Choice cards should be compact (node_id + short label + teaser)

### Versioning

- Use `spec_version` field in KnowledgeQuery to version the protocol
- Set `WeightsVersion` subnet hyperparameter to gate incompatible updates
- Miners can check `spec_version` and respond accordingly

### Timeouts

- `KnowledgeQuery`: 10-15s (vector search is fast)
- `NarrativeHop`: 30-60s (LLM generation is slower)
- `NarrativeHopStream`: 60-120s (streaming allows longer generation)

---

## Sources

- [Synapse Python API](https://docs.learnbittensor.org/python-api/html/autoapi/bittensor/core/synapse/)
- [Axon Python API](https://docs.learnbittensor.org/python-api/html/autoapi/bittensor/core/axon/)
- [Dendrite Python API](https://docs.learnbittensor.org/python-api/html/autoapi/bittensor/core/dendrite/)
- [Subnet Template — protocol.py](https://github.com/opentensor/bittensor-subnet-template/blob/main/template/protocol.py)
