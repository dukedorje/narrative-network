---
name: Traverse mode UI
description: SvelteKit traverse mode built in this session — entry form, choice cards, narrative accumulation
type: project
---

A "Traverse" mode was added to the main page alongside the existing "Explore" mode.

**Why:** To let users traverse the knowledge graph via the gateway session API (/enter, /hop) rather than just browsing it.

**How to apply:** The mode toggle is in the top search bar. Traverse mode shows narrative passages on the left and choice cards on the right. Choice cards use `thematic_color` for left-border accents. Narrative history accumulates — latest passage has green left border.

Key files:
- `src/routes/+page.svelte` — mode toggle, traverse state, handleEnter/handleHop
- `src/routes/api/traverse/enter/+server.ts` — proxies to GATEWAY_URL/enter
- `src/routes/api/traverse/hop/+server.ts` — proxies to GATEWAY_URL/hop
