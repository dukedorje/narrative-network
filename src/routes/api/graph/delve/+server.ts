import { json } from '@sveltejs/kit';
import { searchGraph } from '$lib/server/graph';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request }) => {
	const { query, numResults } = await request.json();

	if (!query) {
		return json({ error: 'query required' }, { status: 400 });
	}

	const result = await searchGraph(query, { numResults: numResults ?? 20 });
	return json(result);
};
