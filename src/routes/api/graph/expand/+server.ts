import { json } from '@sveltejs/kit';
import { expandNode } from '$lib/server/graph';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request }) => {
	const { entityUuid } = await request.json();

	if (!entityUuid) {
		return json({ error: 'entityUuid required' }, { status: 400 });
	}

	const result = await expandNode(entityUuid);
	return json(result);
};
