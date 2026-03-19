# Graph Navigator — Feature Specification

Reference document for rebuilding the knowledge graph browser with Threlte (Three.js).

---

## Overview

The graph navigator is the main page of the BKN web app. It lets users search a knowledge graph and visually explore entities and their relationships. Users search by natural language, see results as a force-directed graph, click nodes to expand their neighborhoods, and read details in a sidebar.

---

## Page Layout (`src/routes/+page.svelte`)

Three-section CSS grid filling `100vh - 65px` (below the app header):

```
┌──────────────────────────────────────────────────┐
│  Search Panel (full width, top)                  │
│  [search input] [Delve button]                   │
│  3 entities · 5 edges · 2 episodes               │
├───────────────────────────────────┬───────────────┤
│                                   │  Info Panel   │
│  Graph Panel                      │  320px wide   │
│  (fills remaining space)          │               │
│                                   │  • Selected   │
│                                   │    node name  │
│                                   │  • Expanded   │
│                                   │    node count │
│                                   │  • Episodes   │
│                                   │  • Entity     │
│                                   │    chips      │
└───────────────────────────────────┴───────────────┘
```

### Search Panel
- Text input with placeholder "Search the knowledge graph..."
- "Delve" submit button (shows "..." while loading)
- Stats row: `{n} entities · {n} edges · {n} episodes`

### Info Panel (right sidebar)
- **Selected node**: name in teal (`#6ee7b7`), count of expanded nodes/edges
- **Episodes**: cards with title, content preview (200 chars), date
- **Entity chips**: pill buttons for each entity; clicking one triggers node expansion

### Graph Panel
- Fills all remaining space; dark radial gradient background
- Houses the graph visualization component

---

## Graph Visualization (currently `ForceGraph.svelte`)

### Data Model

**Input props:**
```ts
entities: Array<{
  uuid: string;
  name: string;
  node_type: string;   // "entity", "episode", etc.
  summary?: string;
  labels?: string[];   // "Entity", "TaxonomyLabel", "Episodic", "episode"
}>

edges: Array<{
  uuid: string;
  edge_type: string;
  source_node_uuid: string;
  target_node_uuid: string;
  fact?: string | null;
}>

onNodeClick?: (uuid: string, name: string) => void
```

**Internal graph nodes:**
```ts
{
  id: string;          // entity UUID
  name: string;
  type: string;        // node_type
  summary?: string;
  labels?: string[];
  radius: number;      // 6 + min(name.length * 0.3, 8) → range 6–14px
}
```

**Internal graph links:**
```ts
{
  id: string;          // edge UUID
  source: string;      // source entity UUID
  target: string;      // target entity UUID
  edgeType: string;
  fact?: string;
}
```

Only edges where both endpoints exist in the entity set are included.

### Visual Design

| Element | Style |
|---------|-------|
| Background | Radial gradient: `#0f172a` center → `#020617` edge |
| Node circles | Radius 6–14px, 85% opacity, `#1e293b` stroke |
| Node hover | 100% opacity, teal stroke `#6ee7b7` |
| Edge lines | `#475569`, 60% opacity, 1.5px stroke |
| Labels | 10px, `#94a3b8`, centered below node, pointer-events none |
| Tooltip | Dark panel `#1e293b`, border `#334155`, max 320px wide |

### Color Scheme (by label/type)

| Label/Type | Color |
|------------|-------|
| Entity | `#6ee7b7` (teal/emerald) |
| TaxonomyLabel | `#93c5fd` (blue) |
| Episodic | `#fbbf24` (amber) |
| episode | `#f97316` (orange) |
| default | `#a78bfa` (purple) |

### Force Simulation Parameters

| Force | Parameter | Value |
|-------|-----------|-------|
| Link | distance | 60 |
| Link | strength | 0.8 |
| Charge (many-body) | strength | -40 |
| Charge | distanceMax | 300 |
| Center | strength | 0.1 |
| Collision | radius | node.radius + 3 |
| X centering | strength | 0.08 |
| Y centering | strength | 0.08 |

Initial node placement: spiral pattern (`angle = i * 0.5`, `r = 20 + i * 3`) from center.

### Interactions

1. **Hover** → tooltip appears near cursor showing:
   - Node name (bold)
   - Summary (first 200 chars, truncated with "...")
   - Labels (comma-separated, in teal)

2. **Click** → fires `onNodeClick(uuid, name)` callback
   - Page handler calls `/api/graph/expand` to fetch neighbors
   - New nodes/edges are merged into the graph (deduplicated by UUID)
   - Selected node highlighted in info panel

3. **Drag** → grab and reposition nodes
   - Drag start: pin node (`fx`/`fy`), restart simulation at `alphaTarget(0.3)`
   - Dragging: update pinned position
   - Drag end: unpin node, let simulation settle (`alphaTarget(0)`)

4. **Zoom & Pan** → scroll to zoom (0.15x–5x), click-drag on background to pan

### Labels
- Only rendered for nodes with `name.length <= 30`
- Truncated to 18 chars + "..." if over 20 chars
- Positioned below node at `radius + 12` px offset

### Responsiveness
- SVG uses `viewBox` matching container dimensions
- `ResizeObserver` triggers full rebuild on container resize
- `$effect` triggers rebuild when `entities` or `edges` data changes

---

## Data Flow

### 1. Page Load
- `+page.server.ts` reads `?q=` query param
- Currently returns empty arrays (Bonfires.ai disabled)
- Page initializes with `data.entities`, `data.edges`, `data.episodes`

### 2. Search (Delve)
```
User types query → submit form
  → POST /api/graph/delve { query, numResults: 30 }
  → Response: { entities[], edges[], episodes[] }
  → Resets expanded nodes; updates graph
```

### 3. Node Expansion
```
User clicks node (or entity chip in sidebar)
  → POST /api/graph/expand { entityUuid, limit: 20 }
  → Response: { success, nodes[], edges[] }
  → New nodes merged (deduplicated by UUID)
  → New edges added
  → Graph re-renders with combined data
```

### 4. State Management
```ts
// Search results (replaced on each search)
searchEntities, searchEdges, searchEpisodes

// Expansion results (accumulated across clicks)
expandedNodes, expandedEdges

// Combined (fed to graph component)
allEntities = [...entities, ...expandedNodes]
allEdges    = [...edges, ...expandedEdges]
```

---

## API Contracts (Zod-validated)

### Delve Request/Response
```ts
// Request
{ query: string, numResults: number, centerNodeUuid?: string }

// Response
{
  success: boolean,
  query: string,
  entities: BonfireEntity[],  // uuid, name, node_type, labels[], summary, attributes
  edges: BonfireEdge[],       // uuid, edge_type, source_node_uuid, target_node_uuid, fact
  episodes: BonfireEpisode[], // uuid, name, content.content, source, created_at
  nodes: BonfireNode[],
  num_results: number,
  new_nodes_count: number,
  new_edges_count: number,
  cached: boolean
}
```

### Expand Request/Response
```ts
// Request
{ entityUuid: string, limit: number }

// Response
{
  success: boolean,
  message: string,
  nodes: BonfireNode[],    // uuid, name, node_type, labels[], summary
  edges: BonfireEdge[],
  episodes: BonfireEpisode[],
  num_results: number
}
```

---

## Styling Constants

All colors reference the Tailwind Slate palette on a dark theme:

| Token | Hex | Usage |
|-------|-----|-------|
| slate-950 | `#020617` | deepest background |
| slate-900 | `#0f172a` | panel backgrounds, gradient center |
| slate-800 | `#1e293b` | cards, tooltip bg, node stroke |
| slate-700 | `#334155` | borders, tooltip border |
| slate-600 | `#475569` | edge lines |
| slate-500 | `#64748b` | muted text (stats, placeholder) |
| slate-400 | `#94a3b8` | secondary text, labels |
| slate-200 | `#e2e8f0` | primary text |
| emerald-300 | `#6ee7b7` | primary accent (selected, hover) |
| emerald-600 | `#059669` | button bg |
| emerald-700 | `#047857` | button hover |
| blue-300 | `#93c5fd` | entity chips, taxonomy nodes |
| amber-400 | `#fbbf24` | episodic nodes |
| orange-400 | `#f97316` | episode nodes |
| violet-400 | `#a78bfa` | default node color |

---

## Files to Replace

| Current File | Role | Threlte Replacement |
|---|---|---|
| `src/lib/components/ForceGraph.svelte` | D3 force graph (SVG) | 3D graph component(s) |
| `src/routes/+page.svelte` | Page layout + state | Keep layout, swap graph component |

### Files to Keep As-Is
- `src/routes/+page.server.ts` — page load
- `src/routes/api/graph/delve/+server.ts` — search endpoint
- `src/routes/api/graph/expand/+server.ts` — expand endpoint
- `src/lib/api/schemas.ts` — Zod schemas
- `src/lib/api/bonfires.ts` — API client
- `src/lib/api/gateway.ts` — gateway client
