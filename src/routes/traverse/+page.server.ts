import type { PageServerLoad } from './$types';
import { env } from '$env/dynamic/private';

const GATEWAY_URL = env.GATEWAY_URL ?? 'http://localhost:8080';

export const load: PageServerLoad = async ({ fetch }) => {
	try {
		const [nodesRes, edgesRes] = await Promise.all([
			fetch(`${GATEWAY_URL}/graph/nodes`),
			fetch(`${GATEWAY_URL}/graph/edges`)
		]);
		const nodes = nodesRes.ok ? await nodesRes.json() : [];
		const edges = edgesRes.ok ? await edgesRes.json() : [];
		return { nodes, edges };
	} catch {
		return { nodes: [], edges: [] };
	}
};
