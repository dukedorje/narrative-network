import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const query = url.searchParams.get('q');

	// Bonfires.ai disabled for demo — return empty graph
	return {
		query,
		entities: [],
		edges: [],
		episodes: [],
		numResults: 0
	};
};
