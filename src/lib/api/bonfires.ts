/**
 * Bonfires.ai TNT v2 client — Zod-validated knowledge graph queries.
 *
 * Drop-in replacement for the original $lib/server/bonfires.ts, now with
 * runtime validation on every response. The old file can be removed once
 * all imports are migrated.
 *
 * @example
 *   import { delve, expandEntity, getEntity } from '$lib/api/bonfires';
 *
 *   const results = await delve({ query: 'quantum computing', numResults: 10 });
 *   const expanded = await expandEntity({ entityUuid: results.entities[0].uuid });
 */

import { env } from '$env/dynamic/private';
import {
	DelveRequest,
	DelveResponse,
	ExpandRequest,
	ExpandResponse,
	BonfireEntity,
	BonfireEdge,
	BonfireEpisode
} from './schemas';
import type {
	DelveRequest as DelveRequestT,
	DelveResponse as DelveResponseT,
	ExpandRequest as ExpandRequestT,
	ExpandResponse as ExpandResponseT,
	BonfireEntity as BonfireEntityT,
	BonfireEdge as BonfireEdgeT,
	BonfireEpisode as BonfireEpisodeT
} from './schemas';

// ── Configuration ───────────────────────────────────────────────────

const BASE_URL = 'https://tnt-v2.api.bonfires.ai';

function getBonfireId(): string {
	return env.BONFIRE_ID ?? '698b70002849d936f4259848';
}

function getAgentId(): string | undefined {
	return env.AGENT_ID || undefined;
}

// ── Error class ─────────────────────────────────────────────────────

export class BonfiresError extends Error {
	constructor(
		public readonly status: number,
		public readonly detail: string,
		public readonly endpoint: string
	) {
		super(`Bonfires API ${endpoint} ${status}: ${detail}`);
		this.name = 'BonfiresError';
	}
}

// ── Internal fetch helper ───────────────────────────────────────────

async function bf<T>(
	path: string,
	schema: { parse: (data: unknown) => T },
	body?: unknown
): Promise<T> {
	const opts: RequestInit = {
		method: body ? 'POST' : 'GET',
		headers: { 'Content-Type': 'application/json' }
	};
	if (body) opts.body = JSON.stringify(body);

	const res = await fetch(`${BASE_URL}${path}`, opts);
	if (!res.ok) {
		const text = await res.text();
		throw new BonfiresError(res.status, text, path);
	}

	const json = await res.json();
	return schema.parse(json);
}

// ── Public API ──────────────────────────────────────────────────────

/**
 * Semantic search across the knowledge graph.
 *
 * Returns entities, edges, episodes, and nodes matching the query.
 * Results are ranked by relevance. Optionally centre the search
 * around a specific node UUID.
 */
export async function delve(input: DelveRequestT): Promise<DelveResponseT> {
	const req = DelveRequest.parse(input);
	return bf('/delve', DelveResponse, {
		query: req.query,
		bonfire_id: getBonfireId(),
		agent_id: getAgentId(),
		num_results: req.numResults,
		center_node_uuid: req.centerNodeUuid
	});
}

/**
 * Expand an entity — returns its connected edges and neighbour nodes.
 *
 * Use this after a user clicks on a node to reveal its local
 * neighbourhood in the force graph.
 */
export async function expandEntity(input: ExpandRequestT): Promise<ExpandResponseT> {
	const req = ExpandRequest.parse(input);
	return bf('/knowledge_graph/expand/entity', ExpandResponse, {
		entity_uuid: req.entityUuid,
		bonfire_id: getBonfireId(),
		limit: req.limit
	});
}

/**
 * Fetch a single entity by UUID.
 */
export async function getEntity(uuid: string): Promise<BonfireEntityT> {
	return bf(`/knowledge_graph/entity/${encodeURIComponent(uuid)}`, BonfireEntity);
}

/**
 * Batch-fetch entities by UUID, optionally including connecting edges.
 */
export async function batchGetEntities(
	uuids: string[],
	includeEdges = false
): Promise<{ entities: BonfireEntityT[]; edges?: BonfireEdgeT[] }> {
	const schema = {
		parse: (data: unknown) => {
			const obj = data as Record<string, unknown>;
			return {
				entities: BonfireEntity.array().parse(obj.entities),
				edges: includeEdges ? BonfireEdge.array().parse(obj.edges) : undefined
			};
		}
	};
	return bf('/knowledge_graph/entities/batch', schema, {
		entity_uuids: uuids,
		include_edges: includeEdges
	});
}

/**
 * Get all episodes (narrative events) attached to a specific node.
 */
export async function getNodeEpisodes(nodeUuid: string): Promise<BonfireEpisodeT[]> {
	return bf(
		`/knowledge_graph/node/${encodeURIComponent(nodeUuid)}/episodes`,
		{ parse: (d: unknown) => BonfireEpisode.array().parse(d) }
	);
}
