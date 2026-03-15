/**
 * Bonfires.ai TNT v2 API client
 *
 * Read-path client for the knowledge graph explorer.
 * Base URL: https://tnt-v2.api.bonfires.ai
 */

import { env } from '$env/dynamic/private';

const BASE_URL = 'https://tnt-v2.api.bonfires.ai';

function getBonfireId(): string {
	// Our bonfire (69b5aa...) requires an API key we don't have yet.
	// Fall back to the public ETHBoulder bonfire for the spike.
	return env.PUBLIC_BONFIRE_ID ?? '698b70002849d936f4259848';
}

function getAgentId(): string | undefined {
	return env.AGENT_ID || undefined;
}

// ── Types ────────────────────────────────────────────────────────────

export interface BonfireEntity {
	uuid: string;
	name: string;
	bonfire_id: string;
	node_type: 'entity';
	labels: string[];
	summary: string;
	attributes: Record<string, unknown>;
	created_at: string;
}

export interface BonfireEdge {
	uuid: string;
	name: string | null;
	fact: string | null;
	bonfire_id: string;
	edge_type: string;
	source_node_uuid: string;
	target_node_uuid: string;
	created_at: string;
	valid_at: string | null;
	expired_at: string | null;
	attributes: Record<string, unknown>;
}

export interface BonfireEpisode {
	uuid: string;
	name: string;
	bonfire_id: string;
	node_type: 'episode';
	source: string;
	source_description: string;
	summary: string | null;
	content: {
		name: string;
		content: string;
		updates?: Array<{ description: string; attributes: Record<string, unknown> }>;
	};
	valid_at: string;
	created_at: string;
	attributes: Record<string, unknown>;
}

export interface BonfireNode {
	uuid: string;
	name: string;
	node_type: string;
	bonfire_id: string;
	labels: string[];
	summary: string;
	attributes: Record<string, unknown>;
	created_at: string;
}

export interface DelveResponse {
	success: boolean;
	query: string;
	num_results: number;
	episodes: BonfireEpisode[];
	entities: BonfireEntity[];
	edges: BonfireEdge[];
	nodes: BonfireNode[];
	graph_id: string | null;
	center_node_uuid: string | null;
	new_nodes_count: number;
	new_edges_count: number;
	cached: boolean;
	error: string | null;
	error_message: string | null;
}

export interface ExpandResponse {
	success: boolean;
	message: string;
	episodes: BonfireEpisode[];
	nodes: BonfireNode[];
	edges: BonfireEdge[];
	graph_id: string | null;
	num_results: number;
}

// ── API Functions ────────────────────────────────────────────────────

async function apiFetch<T>(path: string, body?: unknown): Promise<T> {
	const opts: RequestInit = {
		method: body ? 'POST' : 'GET',
		headers: { 'Content-Type': 'application/json' }
	};
	if (body) opts.body = JSON.stringify(body);

	const res = await fetch(`${BASE_URL}${path}`, opts);
	if (!res.ok) {
		const text = await res.text();
		throw new Error(`Bonfires API ${path} ${res.status}: ${text}`);
	}
	return res.json();
}

/**
 * Unified semantic search across the knowledge graph.
 */
export async function delve(
	query: string,
	opts?: { numResults?: number; centerNodeUuid?: string }
): Promise<DelveResponse> {
	return apiFetch<DelveResponse>('/delve', {
		query,
		bonfire_id: getBonfireId(),
		agent_id: getAgentId(),
		num_results: opts?.numResults ?? 20,
		center_node_uuid: opts?.centerNodeUuid
	});
}

/**
 * Expand an entity node — returns connected edges and nodes.
 */
export async function expandEntity(
	entityUuid: string,
	limit = 50
): Promise<ExpandResponse> {
	return apiFetch<ExpandResponse>('/knowledge_graph/expand/entity', {
		entity_uuid: entityUuid,
		bonfire_id: getBonfireId(),
		limit
	});
}

/**
 * Get a single entity by UUID.
 */
export async function getEntity(uuid: string): Promise<BonfireEntity> {
	return apiFetch<BonfireEntity>(`/knowledge_graph/entity/${uuid}`);
}

/**
 * Batch fetch entities by UUID.
 */
export async function batchGetEntities(
	uuids: string[],
	includeEdges = false
): Promise<{ entities: BonfireEntity[]; edges?: BonfireEdge[] }> {
	return apiFetch('/knowledge_graph/entities/batch', {
		entity_uuids: uuids,
		include_edges: includeEdges
	});
}

/**
 * Get episodes for a specific node.
 */
export async function getNodeEpisodes(nodeUuid: string): Promise<BonfireEpisode[]> {
	return apiFetch<BonfireEpisode[]>(`/knowledge_graph/node/${nodeUuid}/episodes`);
}
