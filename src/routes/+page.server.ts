import { delve } from '$lib/server/bonfires';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const query = url.searchParams.get('q');

	if (!query) {
		// Default: show a broad view of the knowledge graph
		const result = await delve('knowledge graph overview', { numResults: 30 });
		return {
			query: null,
			entities: result.entities,
			edges: result.edges,
			episodes: result.episodes.slice(0, 5),
			numResults: result.num_results
		};
	}

	const result = await delve(query, { numResults: 30 });
	return {
		query,
		entities: result.entities,
		edges: result.edges,
		episodes: result.episodes.slice(0, 10),
		numResults: result.num_results
	};
};
