import { json } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const GATEWAY_URL = env.GATEWAY_URL ?? 'http://localhost:8080';

export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();
	const res = await fetch(`${GATEWAY_URL}/enter`, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
	if (!res.ok) {
		const text = await res.text();
		return json({ error: text }, { status: res.status });
	}
	return json(await res.json());
};
