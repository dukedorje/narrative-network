import { json } from '@sveltejs/kit';
import { expandEntity } from '$lib/server/bonfires';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request }) => {
	const { entityUuid, limit } = await request.json();

	if (!entityUuid) {
		return json({ error: 'entityUuid required' }, { status: 400 });
	}

	const result = await expandEntity(entityUuid, limit ?? 20);
	return json(result);
};
