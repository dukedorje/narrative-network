import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const GATEWAY_URL = env.GATEWAY_URL ?? 'http://localhost:8080';

export const GET: RequestHandler = async ({ url, request }) => {
	const filter = url.searchParams.get('filter');
	const gwUrl = new URL(`${GATEWAY_URL}/events/stream`);
	if (filter) gwUrl.searchParams.set('filter', filter);

	const controller = new AbortController();
	request.signal.addEventListener('abort', () => controller.abort());

	const upstream = await fetch(gwUrl.toString(), {
		signal: controller.signal,
		headers: { Accept: 'text/event-stream' }
	});

	if (!upstream.ok || !upstream.body) {
		return new Response('Gateway unavailable', { status: 502 });
	}

	return new Response(upstream.body, {
		headers: {
			'Content-Type': 'text/event-stream',
			'Cache-Control': 'no-cache',
			Connection: 'keep-alive',
			'X-Accel-Buffering': 'no'
		}
	});
};
