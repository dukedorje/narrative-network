import { getAllNodes, searchGraph } from '$lib/server/graph';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const query = url.searchParams.get('q');

	if (!query) {
		const result = await getAllNodes();
		return {
			query: null,
			entities: result.entities,
			edges: result.edges,
			episodes: result.episodes.slice(0, 5),
			numResults: result.num_results
		};
	}

	const result = await searchGraph(query, { numResults: 30 });
	return {
		query,
		entities: result.entities,
		edges: result.edges,
		episodes: result.episodes.slice(0, 10),
		numResults: result.num_results
	};
};
