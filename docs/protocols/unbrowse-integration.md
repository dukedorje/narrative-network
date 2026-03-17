# Unbrowse Integration

**Service:** [unbrowse.ai](https://unbrowse.ai)
**Role:** External web context and action layer for knowledge not in the graph.

## Overview

Unbrowse serves as the data/action fallback layer for Narrative Network. When a query reaches the system that has no adequate coverage in the knowledge graph (low corpus similarity, no miner with a matching domain, or a newly proposed node that needs domain validation), Unbrowse fetches live web context to supplement in-graph knowledge.

The `orchestrator/unbrowse.py` module provides an async HTTP client (`UnbrowseClient`) used across the stack. All calls are non-blocking — errors return empty results so the main traversal flow is never degraded by external availability.

## Integration points

### Unified Miner (`domain/unified_miner.py`)

**KnowledgeQuery handler:** When `domain_similarity < UNBROWSE_CORPUS_THRESHOLD` (default 0.35), the miner fetches 2 web context chunks via Unbrowse and appends them to `synapse.chunks`. This supplements sparse corpora with live web data without requiring a full corpus rebuild.

**NarrativeHop handler:** Before generating hop text, the miner fetches up to 2 Unbrowse context snippets scoped to `destination_node_id`. Results are injected as a synthetic retrieved chunk so the LLM has real-world grounding for narrative generation.

### Integration Manager (`evolution/integration.py`)
On `IntegrationManager.enqueue` (FORESHADOW phase), a fire-and-forget prefetch fetches external context for the new node's domain. This pre-seeds miner operators with relevant web content before the node goes BRIDGE.

### Proposal Submitter (`evolution/proposal.py`)
For `ADD_NODE` proposals, `validate_domain_coverage(domain, node_id)` returns a confidence score. If coverage is below threshold, operators are warned that the domain may not have sufficient real-world content to sustain a knowledge graph node.

### Gateway (`orchestrator/gateway.py`)
Future integration point: when all miners respond with `domain_similarity < threshold`, the gateway can use Unbrowse to synthesize an entry point response. Noted as `TODO: unbrowse_fallback_enter` in the gateway.

## Configuration

```
UNBROWSE_API_KEY=<your_key>              # Required for live fetches
AXON_UNBROWSE_API_URL=https://...        # Override default Unbrowse endpoint
AXON_UNBROWSE_TIMEOUT_S=8.0             # Per-request timeout (seconds)
AXON_UNBROWSE_CORPUS_THRESHOLD=0.35     # Domain similarity below this triggers fallback
```

## API shape (Unbrowse v1)

```
POST /v1/context
{
  "query": "quantum entanglement overview",
  "scope": "physics-01",        // optional node_id scoping
  "max_results": 3
}

-> 200 OK
{
  "results": [
    {
      "url": "https://...",
      "content": "...",
      "source_type": "web_page",
      "confidence": 0.87
    }
  ]
}
```

## Non-blocking design

Every `UnbrowseClient` method catches all exceptions and returns `[]` on failure. The `UNBROWSE_API_KEY` env var is required — without it, all calls are no-ops (debug log only). This prevents external API availability from impacting subnet scoring or traversal latency.
