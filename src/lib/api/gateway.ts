/**
 * Gateway client — typed, validated access to the Python traversal API.
 *
 * Talks to the FastAPI gateway (orchestrator/gateway.py) which manages
 * sessions, broadcasts to miners, and generates narrative hops.
 *
 * All responses are Zod-validated at runtime so callers get real types,
 * never `any`. Errors surface as thrown `GatewayError` instances.
 *
 * @example
 *   import { enterSession, hop, getSession } from '$lib/api/gateway';
 *
 *   const session = await enterSession({ query_text: 'Tell me about philosophy' });
 *   const next = await hop({
 *     session_id: session.session_id,
 *     destination_node_id: session.choice_cards![0].destination_node_id
 *   });
 */

import { env } from '$env/dynamic/private';
import {
	EnterRequest,
	EnterResponse,
	HopRequest,
	HopResponse,
	SessionResponse,
	HealthResponse,
	GraphNode
} from './schemas';
import type {
	EnterRequest as EnterRequestT,
	EnterResponse as EnterResponseT,
	HopRequest as HopRequestT,
	HopResponse as HopResponseT,
	SessionResponse as SessionResponseT,
	HealthResponse as HealthResponseT,
	GraphNode as GraphNodeT
} from './schemas';

// ── Configuration ───────────────────────────────────────────────────

/** Gateway base URL. Set GATEWAY_URL in .env (defaults to local dev). */
function getBaseUrl(): string {
	return env.GATEWAY_URL ?? 'http://localhost:8080';
}

// ── Error class ─────────────────────────────────────────────────────

export class GatewayError extends Error {
	constructor(
		public readonly status: number,
		public readonly detail: string,
		public readonly endpoint: string
	) {
		super(`Gateway ${endpoint} ${status}: ${detail}`);
		this.name = 'GatewayError';
	}
}

// ── Internal fetch helper ───────────────────────────────────────────

async function gw<T>(
	path: string,
	schema: { parse: (data: unknown) => T },
	body?: unknown
): Promise<T> {
	const opts: RequestInit = {
		method: body ? 'POST' : 'GET',
		headers: { 'Content-Type': 'application/json' }
	};
	if (body) opts.body = JSON.stringify(body);

	const res = await fetch(`${getBaseUrl()}${path}`, opts);
	if (!res.ok) {
		const text = await res.text();
		let detail: string;
		try {
			detail = JSON.parse(text).detail ?? text;
		} catch {
			detail = text;
		}
		throw new GatewayError(res.status, detail, path);
	}

	const json = await res.json();
	return schema.parse(json);
}

// ── Public API ──────────────────────────────────────────────────────
// Each function validates inputs AND outputs via Zod.

/**
 * Start a new traversal session.
 *
 * Sends the player's query to the gateway, which ranks entry nodes
 * by corpus similarity, picks the best one, and generates an opening
 * narrative passage with choice cards for the first hop.
 *
 * @throws {GatewayError} 503 — no active miners or no entry nodes resolved
 * @throws {GatewayError} 500 — narrative generation failed on the miner
 */
export async function enterSession(input: EnterRequestT): Promise<EnterResponseT> {
	const body = EnterRequest.parse(input);
	return gw('/enter', EnterResponse, body);
}

/**
 * Advance the traversal to a destination node.
 *
 * The gateway resolves a narrative miner for the target node, retrieves
 * corpus chunks, and generates the next passage + choice cards. The
 * session transitions to "terminal" when no unvisited neighbours remain.
 *
 * @throws {GatewayError} 404 — session not found
 * @throws {GatewayError} 409 — session not in "active" state
 * @throws {GatewayError} 503 — no miner found for destination node
 */
export async function hop(input: HopRequestT): Promise<HopResponseT> {
	const body = HopRequest.parse(input);
	return gw('/hop', HopResponse, body);
}

/**
 * Read a session's current state without advancing it.
 *
 * Useful for reconnecting to an in-progress session or checking
 * whether the traversal has reached a terminal state.
 *
 * @throws {GatewayError} 404 — session not found
 */
export async function getSession(sessionId: string): Promise<SessionResponseT> {
	return gw(`/session/${encodeURIComponent(sessionId)}`, SessionResponse);
}

/**
 * Gateway health check.
 *
 * Returns netuid, active/total session counts. In dev mode the
 * response includes additional graph_stats and loaded_corpus_nodes.
 */
export async function health(): Promise<HealthResponseT> {
	return gw('/healthz', HealthResponse);
}

/**
 * List all graph nodes with corpus status and neighbours (dev mode only).
 *
 * Only available when the gateway runs with AXON_NETWORK=local.
 */
export async function getGraphNodes(): Promise<GraphNodeT[]> {
	return gw('/graph/nodes', { parse: (d: unknown) => GraphNode.array().parse(d) });
}
