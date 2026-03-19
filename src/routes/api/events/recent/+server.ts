import { env } from '$env/dynamic/private';
import { json } from '@sveltejs/kit';
import { EventsRecentResponse } from '$lib/api/schemas';
import type { RequestHandler } from './$types';

const GATEWAY_URL = env.GATEWAY_URL ?? 'http://localhost:8080';

export const GET: RequestHandler = async ({ url }) => {
	const limit = url.searchParams.get('limit') ?? '50';
	const component = url.searchParams.get('component');
	const params = new URLSearchParams({ limit });
	if (component) params.set('component', component);

	const res = await fetch(`${GATEWAY_URL}/events/recent?${params}`);
	if (!res.ok) {
		return json({ events: [] }, { status: res.status });
	}

	const data = await res.json();
	const validated = EventsRecentResponse.parse(data);
	return json(validated);
};
