import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

// Bonfires.ai disabled for demo — return empty results
export const POST: RequestHandler = async ({ request }) => {
	const { query } = await request.json();

	return json({
		success: true,
		query: query ?? '',
		num_results: 0,
		episodes: [],
		entities: [],
		edges: [],
		nodes: [],
		graph_id: null,
		center_node_uuid: null,
		new_nodes_count: 0,
		new_edges_count: 0,
		cached: false,
		error: null,
		error_message: null
	});
};
