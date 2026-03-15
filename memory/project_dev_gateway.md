---
name: Dev gateway setup
description: How to run the gateway locally without Bittensor
type: project
---

The gateway has a standalone dev mode that doesn't require Bittensor wallet/subtensor.

Run with:
```
AXON_NETWORK=local uv run python -m orchestrator.gateway
```

This calls `create_dev_app()` which:
- Creates an in-memory GraphStore
- Seeds it with `load_topology()` (16 nodes from seed/topology.yaml)
- Registers all graph browsing endpoints
- Registers dev stub /enter and /hop endpoints (no miners needed, generates narrative from node metadata)
- Wires TraversalArbiter (stub mode without NLA_API_KEY)

SvelteKit dev server runs separately on :5173. Set GATEWAY_URL=http://localhost:8080 in .env.
