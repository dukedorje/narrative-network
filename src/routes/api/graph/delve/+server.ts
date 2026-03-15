import { json } from '@sveltejs/kit';
import { delve } from '$lib/server/bonfires';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request }) => {
	const { query, numResults, centerNodeUuid } = await request.json();

	if (!query) {
		return json({ error: 'query required' }, { status: 400 });
	}

	const result = await delve(query, { numResults: numResults ?? 20, centerNodeUuid });
	return json(result);
};
