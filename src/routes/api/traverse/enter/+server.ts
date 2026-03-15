import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

const GATEWAY_URL = process.env.GATEWAY_URL ?? 'http://localhost:8080';

export const POST: RequestHandler = async ({ request }) => {
	const body = await request.json();
	try {
		const res = await fetch(`${GATEWAY_URL}/enter`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(body)
		});
		if (!res.ok) {
			const err = await res.json().catch(() => ({ detail: res.statusText }));
			return json({ error: err.detail ?? 'Gateway error' }, { status: res.status });
		}
		return json(await res.json());
	} catch {
		return json({ error: 'Gateway unavailable' }, { status: 503 });
	}
};
