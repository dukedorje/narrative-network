/**
 * BKN API — public barrel export
 *
 * This is the single import point for frontend devs:
 *
 *   import { enterSession, hop, delve } from '$lib/api';
 *   import type { ChoiceCard, EnterResponse } from '$lib/api';
 *
 * ┌─────────────────────────────────────────────────────────────────┐
 * │  FUNCTION REFERENCE                                            │
 * ├─────────────────────────────────────────────────────────────────┤
 * │                                                                │
 * │  Gateway (Python traversal API)                                │
 * │  ─────────────────────────────                                 │
 * │  enterSession(req)    Start a traversal session with a query   │
 * │  hop(req)             Advance to a chosen destination node     │
 * │  getSession(id)       Read session state (no side effects)     │
 * │  health()             Gateway health + session counts          │
 * │  getGraphNodes()      List graph nodes (dev mode only)         │
 * │                                                                │
 * │  Bonfires.ai (knowledge graph search)                          │
 * │  ───────────────────────────────────                           │
 * │  delve(req)           Semantic search across the graph         │
 * │  expandEntity(req)    Expand a node's neighbourhood            │
 * │  getEntity(uuid)      Fetch a single entity                    │
 * │  batchGetEntities()   Batch-fetch entities by UUID             │
 * │  getNodeEpisodes()    Get narrative episodes for a node        │
 * │                                                                │
 * └─────────────────────────────────────────────────────────────────┘
 */

// Gateway — traversal session lifecycle
export { enterSession, hop, getSession, health, getGraphNodes, GatewayError } from './gateway';

// Bonfires — knowledge graph search
export { delve, expandEntity, getEntity, batchGetEntities, getNodeEpisodes, BonfiresError } from './bonfires';

// Schemas (for manual validation, form builders, etc.)
export {
	// Primitives
	NodeId,
	SessionId,
	SessionState,
	ChoiceCard,

	// Gateway schemas
	EnterRequest,
	EnterResponse,
	HopRequest,
	HopResponse,
	SessionResponse,
	HealthResponse,
	DevHealthResponse,
	GraphNode,

	// WebSocket schemas
	WsHopCommand,
	WsServerMessage,

	// Bonfires schemas
	BonfireEntity,
	BonfireEdge,
	BonfireEpisode,
	BonfireNode,
	DelveRequest,
	DelveResponse,
	ExpandRequest,
	ExpandResponse
} from './schemas';

// Re-export all inferred types
export type {
	NodeId as NodeIdT,
	SessionId as SessionIdT,
	SessionState as SessionStateT,
	ChoiceCard as ChoiceCardT,
	EnterRequest as EnterRequestT,
	EnterResponse as EnterResponseT,
	HopRequest as HopRequestT,
	HopResponse as HopResponseT,
	SessionResponse as SessionResponseT,
	HealthResponse as HealthResponseT,
	DevHealthResponse as DevHealthResponseT,
	GraphNode as GraphNodeT,
	WsHopCommand as WsHopCommandT,
	WsServerMessage as WsServerMessageT,
	BonfireEntity as BonfireEntityT,
	BonfireEdge as BonfireEdgeT,
	BonfireEpisode as BonfireEpisodeT,
	BonfireNode as BonfireNodeT,
	DelveRequest as DelveRequestT,
	DelveResponse as DelveResponseT,
	ExpandRequest as ExpandRequestT,
	ExpandResponse as ExpandResponseT
} from './schemas';
