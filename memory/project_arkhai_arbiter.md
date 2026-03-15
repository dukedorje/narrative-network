---
name: Arkhai traversal arbiter
description: TraversalArbiter filters next-hop choice cards via Arkhai NLA on each hop
type: project
---

Integrated Arkhai arbiter into the hop selection flow.

**Why:** When a user selects a choice card, an Arkhai arbiter should validate the hop and filter the next candidate set to meaningful forward steps, not just raw graph neighbours.

**How to apply:** `TraversalArbiter.check_hop()` in `orchestrator/arbiter.py` is called in both dev and production hop endpoints after the hop is resolved. It sends a natural language demand to `POST /v1/arbitrate` on the Arkhai NLA service. Falls back to full neighbour list if NLA_API_KEY is absent.

The arbiter's `reasoning` surfaces as `knowledge_synthesis` in the hop response, shown below the narrative in the UI.

Requires `NLA_API_KEY` env var for live arbitration. Works without it in dev (stub passthrough).
