import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

// Bonfires.ai disabled for demo — return empty results
export const POST: RequestHandler = async ({ request }) => {
	const { entityUuid } = await request.json();

	if (!entityUuid) {
		return json({ error: 'entityUuid required' }, { status: 400 });
	}

	return json({
		success: true,
		message: 'Bonfires.ai disabled for demo',
		episodes: [],
		nodes: [],
		edges: [],
		graph_id: null,
		num_results: 0
	});
};
