---
name: Graph browsing API (corpora replacement)
description: Gateway graph endpoints replacing Bonfires external API with subnet's own knowledge graph
type: project
---

Replaced Bonfires.ai external API with the subnet's own graph data.

**Why:** Explore mode should show the subnet's 16 seed nodes, not an external knowledge graph.

**How to apply:** The SvelteKit frontend now calls the gateway for graph data. Bonfires.ts is no longer used.

New gateway endpoints (registered via `_register_graph_endpoints`):
- `GET /graph/nodes` — all live nodes + edges + recent traversal sessions
- `POST /graph/search` — keyword search over node IDs and descriptions
- `GET /graph/node/{id}/expand` — node neighbours + connecting edges

New TypeScript file: `src/lib/server/graph.ts` — replaces bonfires.ts
Updated: `+page.server.ts`, `api/graph/delve/+server.ts`, `api/graph/expand/+server.ts`

GATEWAY_URL env var (default http://localhost:8080) controls where SvelteKit calls.
Dev gateway seeds topology via `load_topology()` on startup.
