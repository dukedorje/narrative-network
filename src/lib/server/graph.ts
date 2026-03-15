/**
 * Client for the Narrative Network gateway graph browsing endpoints.
 * Replaces the Bonfires.ai external API with the subnet's own knowledge graph.
 */

const GATEWAY_URL = process.env.GATEWAY_URL ?? 'http://localhost:8080';

export interface GraphEntity {
	uuid: string;
	name: string;
	node_type: string;
	labels: string[];
	summary: string;
	created_at: number;
}

export interface GraphEdge {
	uuid: string;
	edge_type: string;
	source_node_uuid: string;
	target_node_uuid: string;
	fact: string | null;
	weight?: number;
}

export interface GraphEpisode {
	uuid: string;
	name: string;
	content: { content: string };
	created_at: number;
}

export interface GraphResult {
	success: boolean;
	entities: GraphEntity[];
	edges: GraphEdge[];
	episodes: GraphEpisode[];
	num_results: number;
	error?: string | null;
}

export interface ExpandResult {
	success: boolean;
	nodes: GraphEntity[];
	edges: GraphEdge[];
	num_results: number;
}

export async function getAllNodes(): Promise<GraphResult> {
	try {
		const res = await fetch(`${GATEWAY_URL}/graph/nodes`);
		if (!res.ok) {
			return empty(`HTTP ${res.status}`);
		}
		return res.json();
	} catch {
		return empty('Gateway unavailable');
	}
}

export async function searchGraph(
	query: string,
	opts: { numResults?: number } = {}
): Promise<GraphResult> {
	try {
		const res = await fetch(`${GATEWAY_URL}/graph/search`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ query, num_results: opts.numResults ?? 20 })
		});
		if (!res.ok) {
			return empty(`HTTP ${res.status}`);
		}
		return res.json();
	} catch {
		return empty('Gateway unavailable');
	}
}

export async function expandNode(nodeId: string): Promise<ExpandResult> {
	try {
		const res = await fetch(
			`${GATEWAY_URL}/graph/node/${encodeURIComponent(nodeId)}/expand`
		);
		if (!res.ok) {
			return { success: false, nodes: [], edges: [], num_results: 0 };
		}
		return res.json();
	} catch {
		return { success: false, nodes: [], edges: [], num_results: 0 };
	}
}

function empty(error: string): GraphResult {
	return { success: false, entities: [], edges: [], episodes: [], num_results: 0, error };
}
