import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const GATEWAY_URL = env.GATEWAY_URL ?? 'http://localhost:8080';

export const GET: RequestHandler = async () => {
	const res = await fetch(`${GATEWAY_URL}/graph/edges`);
	if (!res.ok) {
		const text = await res.text();
		return json({ error: text }, { status: res.status });
	}
	return json(await res.json());
};
