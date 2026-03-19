/**
 * BKN — Zod-validated API boundary
 *
 * Single source of truth for all request/response shapes between the
 * SvelteKit frontend and the Python gateway + Bonfires.ai APIs.
 *
 * Usage:
 *   import { enterSession, hop, getSession } from '$lib/api/gateway';
 *   import { delve, expandEntity } from '$lib/api/bonfires';
 *
 * Every function validates responses at runtime so the frontend never
 * receives untyped data. Inferred types are re-exported for convenience.
 */

import { z } from 'zod';

// ── Primitives ──────────────────────────────────────────────────────

/** Miner-assigned node identifier (e.g. "philosophy", "node-0") */
export const NodeId = z.string().min(1);

/** UUID session identifier */
export const SessionId = z.string().uuid();

/** Session lifecycle state */
export const SessionState = z.enum(['created', 'active', 'terminal', 'error']);

// ── Choice Card ─────────────────────────────────────────────────────

/** A navigable option presented to the player after each hop */
export const ChoiceCard = z.object({
	/** Human-readable label for this choice */
	text: z.string(),
	/** Target node the player will traverse to */
	destination_node_id: NodeId,
	/** How much this traversal reinforces the edge (0.0–1.0) */
	edge_weight_delta: z.number().min(0).max(1),
	/** Hex colour hinting at thematic mood, e.g. "#7c3aed" */
	thematic_color: z.string().regex(/^#[0-9a-fA-F]{6}$/)
});

// ── Gateway: /enter ─────────────────────────────────────────────────

/** Start a new traversal session by submitting a natural-language query */
export const EnterRequest = z.object({
	/** The player's opening query / topic of interest */
	query_text: z.string().min(1),
	/** How many candidate entry-nodes to rank (default 3) */
	top_k_entry: z.number().int().positive().default(3)
});

export const EnterResponse = z.object({
	session_id: SessionId,
	/** Node the player landed on */
	current_node_id: NodeId.nullable(),
	/** Opening narrative passage (100–500 words) */
	narrative_passage: z.string().nullable(),
	/** Available next moves */
	choice_cards: z.array(ChoiceCard).nullable(),
	/** Compressed summary of the passage */
	knowledge_synthesis: z.string().nullable(),
	/** Ordered list of visited node IDs */
	player_path: z.array(NodeId),
	state: SessionState
});

// ── Gateway: /hop ───────────────────────────────────────────────────

/** Advance the traversal to a chosen destination node */
export const HopRequest = z.object({
	/** Active session from a prior /enter call */
	session_id: SessionId,
	/** Node to traverse to (must be in the current choice_cards) */
	destination_node_id: NodeId
});

export const HopResponse = z.object({
	session_id: SessionId,
	current_node_id: NodeId.nullable(),
	/** Narrative continuation (100–500 words) */
	narrative_passage: z.string().nullable(),
	choice_cards: z.array(ChoiceCard).nullable(),
	knowledge_synthesis: z.string().nullable(),
	player_path: z.array(NodeId),
	state: SessionState,
	/** Non-null when the hop was rejected (e.g. node already visited) */
	error: z.string().nullable().optional()
});

// ── Gateway: /session/:id ───────────────────────────────────────────

/** Read-only snapshot of a session's current state */
export const SessionResponse = z.object({
	session_id: SessionId,
	state: SessionState,
	current_node_id: NodeId.nullable(),
	player_path: z.array(NodeId),
	choice_cards: z.array(ChoiceCard).nullable().optional(),
	/** Unix timestamp — session creation */
	created_at: z.number().optional(),
	/** Unix timestamp — last state change */
	updated_at: z.number().optional()
});

// ── Gateway: /healthz ───────────────────────────────────────────────

export const HealthResponse = z.object({
	status: z.literal('ok'),
	netuid: z.number(),
	active_sessions: z.number().int().nonnegative(),
	total_sessions: z.number().int().nonnegative()
});

/** Dev-mode extended health (includes graph_stats, loaded_corpus_nodes) */
export const DevHealthResponse = HealthResponse.omit({ active_sessions: true, total_sessions: true }).extend({
	mode: z.literal('dev'),
	graph_stats: z.record(z.string(), z.unknown()),
	loaded_corpus_nodes: z.array(z.string())
});

// ── Gateway: /graph/stats & /graph/nodes (dev mode) ─────────────────

export const GraphNode = z.object({
	node_id: NodeId,
	has_corpus: z.boolean(),
	neighbours: z.array(NodeId)
});

// ── WebSocket: /session/:id/live ────────────────────────────────────

/** Client → server message over the live session WebSocket */
export const WsHopCommand = z.object({
	destination_node_id: NodeId
});

/** Server → client: either a hop result, ping, or error */
export const WsServerMessage = z.union([
	HopResponse,
	z.object({ type: z.literal('ping') }),
	z.object({ error: z.string() })
]);

// ── Events: /events/stream (SSE) + /events/recent ──────────────────

export const NetworkEvent = z.object({
	event_type: z.string(),
	source: z.string(),
	payload: z.record(z.string(), z.unknown()),
	correlation_id: z.string(),
	timestamp: z.number()
});

export const EventsRecentResponse = z.object({
	events: z.array(NetworkEvent)
});

// ── Bonfires.ai: shared shapes ──────────────────────────────────────

export const BonfireEntity = z.object({
	uuid: z.string().uuid(),
	name: z.string(),
	bonfire_id: z.string(),
	node_type: z.literal('entity'),
	labels: z.array(z.string()),
	summary: z.string(),
	attributes: z.record(z.string(), z.unknown()),
	created_at: z.string()
});

export const BonfireEdge = z.object({
	uuid: z.string().uuid(),
	name: z.string().nullable(),
	fact: z.string().nullable(),
	bonfire_id: z.string(),
	edge_type: z.string(),
	source_node_uuid: z.string().uuid(),
	target_node_uuid: z.string().uuid(),
	created_at: z.string(),
	valid_at: z.string().nullable(),
	expired_at: z.string().nullable(),
	attributes: z.record(z.string(), z.unknown())
});

export const BonfireEpisode = z.object({
	uuid: z.string().uuid(),
	name: z.string(),
	bonfire_id: z.string(),
	node_type: z.literal('episode'),
	source: z.string(),
	source_description: z.string(),
	summary: z.string().nullable(),
	content: z.object({
		name: z.string(),
		content: z.string(),
		updates: z
			.array(
				z.object({
					description: z.string(),
					attributes: z.record(z.string(), z.unknown())
				})
			)
			.optional()
	}),
	valid_at: z.string(),
	created_at: z.string(),
	attributes: z.record(z.string(), z.unknown())
});

export const BonfireNode = z.object({
	uuid: z.string().uuid(),
	name: z.string(),
	node_type: z.string(),
	bonfire_id: z.string(),
	labels: z.array(z.string()),
	summary: z.string(),
	attributes: z.record(z.string(), z.unknown()),
	created_at: z.string()
});

// ── Bonfires.ai: /delve ─────────────────────────────────────────────

export const DelveRequest = z.object({
	/** Natural-language search query */
	query: z.string().min(1),
	/** Max results to return (default 20) */
	numResults: z.number().int().positive().default(20),
	/** Optional UUID to centre the search around */
	centerNodeUuid: z.string().uuid().optional()
});

export const DelveResponse = z.object({
	success: z.boolean(),
	query: z.string(),
	num_results: z.number(),
	episodes: z.array(BonfireEpisode),
	entities: z.array(BonfireEntity),
	edges: z.array(BonfireEdge),
	nodes: z.array(BonfireNode),
	graph_id: z.string().nullable(),
	center_node_uuid: z.string().nullable(),
	new_nodes_count: z.number(),
	new_edges_count: z.number(),
	cached: z.boolean(),
	error: z.string().nullable(),
	error_message: z.string().nullable()
});

// ── Bonfires.ai: /expand ────────────────────────────────────────────

export const ExpandRequest = z.object({
	/** UUID of the entity to expand */
	entityUuid: z.string().uuid(),
	/** Max connected nodes to return (default 20) */
	limit: z.number().int().positive().default(20)
});

export const ExpandResponse = z.object({
	success: z.boolean(),
	message: z.string(),
	episodes: z.array(BonfireEpisode),
	nodes: z.array(BonfireNode),
	edges: z.array(BonfireEdge),
	graph_id: z.string().nullable(),
	num_results: z.number()
});

// ── Inferred TypeScript types ───────────────────────────────────────

export type NodeId = z.infer<typeof NodeId>;
export type SessionId = z.infer<typeof SessionId>;
export type SessionState = z.infer<typeof SessionState>;
export type ChoiceCard = z.infer<typeof ChoiceCard>;

export type EnterRequest = z.infer<typeof EnterRequest>;
export type EnterResponse = z.infer<typeof EnterResponse>;
export type HopRequest = z.infer<typeof HopRequest>;
export type HopResponse = z.infer<typeof HopResponse>;
export type SessionResponse = z.infer<typeof SessionResponse>;
export type HealthResponse = z.infer<typeof HealthResponse>;
export type DevHealthResponse = z.infer<typeof DevHealthResponse>;
export type GraphNode = z.infer<typeof GraphNode>;

export type WsHopCommand = z.infer<typeof WsHopCommand>;
export type WsServerMessage = z.infer<typeof WsServerMessage>;

export type BonfireEntity = z.infer<typeof BonfireEntity>;
export type BonfireEdge = z.infer<typeof BonfireEdge>;
export type BonfireEpisode = z.infer<typeof BonfireEpisode>;
export type BonfireNode = z.infer<typeof BonfireNode>;
export type DelveRequest = z.infer<typeof DelveRequest>;
export type DelveResponse = z.infer<typeof DelveResponse>;
export type ExpandRequest = z.infer<typeof ExpandRequest>;
export type ExpandResponse = z.infer<typeof ExpandResponse>;

export type NetworkEvent = z.infer<typeof NetworkEvent>;
export type EventsRecentResponse = z.infer<typeof EventsRecentResponse>;
