<script lang="ts">
	import GraphCanvas from '$lib/components/graph/GraphCanvas.svelte';

	let { data } = $props();

	let searchQuery = $state(data.query ?? '');
	let searchEntities = $state<typeof data.entities | null>(null);
	let searchEdges = $state<typeof data.edges | null>(null);
	let searchEpisodes = $state<typeof data.episodes | null>(null);
	let entities = $derived(searchEntities ?? data.entities);
	let edges = $derived(searchEdges ?? data.edges);
	let episodes = $derived(searchEpisodes ?? data.episodes);
	let loading = $state(false);
	let selectedNode = $state<{ uuid: string; name: string } | null>(null);
	let expandedNodes = $state<
		Array<{ uuid: string; name: string; node_type: string; summary?: string }>
	>([]);
	let expandedEdges = $state<
		Array<{
			uuid: string;
			edge_type: string;
			source_node_uuid: string;
			target_node_uuid: string;
			fact?: string | null;
		}>
	>([]);

	async function handleSearch(e: SubmitEvent) {
		e.preventDefault();
		if (!searchQuery.trim()) return;
		loading = true;
		selectedNode = null;

		try {
			const res = await fetch('/api/graph/delve', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ query: searchQuery, numResults: 30 })
			});
			const result = await res.json();
			searchEntities = result.entities ?? [];
			searchEdges = result.edges ?? [];
			searchEpisodes = (result.episodes ?? []).slice(0, 10);
			// Merge expanded data
			expandedNodes = [];
			expandedEdges = [];
		} catch (err) {
			console.error('Search failed:', err);
		} finally {
			loading = false;
		}
	}

	async function handleNodeClick(uuid: string, name: string) {
		selectedNode = { uuid, name };
		loading = true;

		try {
			const res = await fetch('/api/graph/expand', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ entityUuid: uuid, limit: 20 })
			});
			const result = await res.json();
			if (result.success) {
				// Merge new nodes/edges into the graph
				const existingUuids = new Set(entities.map((e) => e.uuid));
				const newEntities = (result.nodes ?? []).filter(
					(n: { uuid: string }) => !existingUuids.has(n.uuid)
				);
				expandedNodes = newEntities;
				expandedEdges = result.edges ?? [];
			}
		} catch (err) {
			console.error('Expand failed:', err);
		} finally {
			loading = false;
		}
	}

	let allEntities = $derived([...entities, ...expandedNodes]);
	let allEdges = $derived([...edges, ...expandedEdges]);
</script>

<div class="explorer">
	<section class="search-panel">
		<form onsubmit={handleSearch}>
			<input
				type="text"
				bind:value={searchQuery}
				placeholder="Search the knowledge graph..."
				class="search-input"
			/>
			<button type="submit" class="search-btn" disabled={loading}>
				{loading ? '...' : 'Delve'}
			</button>
		</form>

		<div class="stats">
			<span>{allEntities.length} entities</span>
			<span>{allEdges.length} edges</span>
			<span>{episodes.length} episodes</span>
		</div>
	</section>

	<section class="graph-panel">
		<GraphCanvas entities={allEntities} edges={allEdges} onNodeClick={handleNodeClick} />
	</section>

	<section class="info-panel">
		{#if selectedNode}
			<div class="selected-node">
				<h3>{selectedNode.name}</h3>
				{#if expandedNodes.length > 0}
					<p class="expand-info">
						+{expandedNodes.length} connected nodes, {expandedEdges.length} edges
					</p>
				{/if}
			</div>
		{/if}

		{#if episodes.length > 0}
			<div class="episodes">
				<h3>Episodes</h3>
				{#each episodes as ep}
					<div class="episode-card">
						<h4>{ep.name}</h4>
						{#if ep.content?.content}
							<p>{ep.content.content.slice(0, 200)}...</p>
						{/if}
						<time>{new Date(ep.created_at).toLocaleDateString()}</time>
					</div>
				{/each}
			</div>
		{/if}

		{#if entities.length > 0}
			<div class="entity-list">
				<h3>Entities</h3>
				{#each entities as entity}
					<button class="entity-chip" onclick={() => handleNodeClick(entity.uuid, entity.name)}>
						{entity.name}
					</button>
				{/each}
			</div>
		{/if}
	</section>
</div>

<style>
	.explorer {
		flex: 1;
		display: grid;
		grid-template-rows: auto 1fr;
		grid-template-columns: 1fr 320px;
		gap: 0;
		height: calc(100vh - 65px);
	}

	.search-panel {
		grid-column: 1 / -1;
		padding: 16px 24px;
		border-bottom: 1px solid #1e293b;
		background: #0f172a;
	}

	form {
		display: flex;
		gap: 8px;
	}

	.search-input {
		flex: 1;
		padding: 10px 16px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		color: #e2e8f0;
		font-size: 15px;
		outline: none;
		transition: border-color 0.2s;
	}

	.search-input:focus {
		border-color: #6ee7b7;
	}

	.search-input::placeholder {
		color: #64748b;
	}

	.search-btn {
		padding: 10px 24px;
		background: #059669;
		color: white;
		border: none;
		border-radius: 8px;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.2s;
	}

	.search-btn:hover {
		background: #047857;
	}

	.search-btn:disabled {
		opacity: 0.5;
		cursor: wait;
	}

	.stats {
		display: flex;
		gap: 16px;
		margin-top: 8px;
		font-size: 13px;
		color: #64748b;
	}

	.graph-panel {
		overflow: hidden;
	}

	.info-panel {
		border-left: 1px solid #1e293b;
		background: #0f172a;
		overflow-y: auto;
		padding: 16px;
	}

	.selected-node h3 {
		font-size: 16px;
		color: #6ee7b7;
		margin: 0 0 8px;
	}

	.expand-info {
		font-size: 13px;
		color: #64748b;
		margin: 0 0 16px;
	}

	.episodes h3,
	.entity-list h3 {
		font-size: 14px;
		color: #94a3b8;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 16px 0 8px;
	}

	.episode-card {
		background: #1e293b;
		border-radius: 8px;
		padding: 12px;
		margin-bottom: 8px;
	}

	.episode-card h4 {
		font-size: 13px;
		color: #e2e8f0;
		margin: 0 0 6px;
		line-height: 1.3;
	}

	.episode-card p {
		font-size: 12px;
		color: #94a3b8;
		margin: 0 0 6px;
		line-height: 1.4;
	}

	.episode-card time {
		font-size: 11px;
		color: #475569;
	}

	.entity-chip {
		display: inline-block;
		padding: 4px 12px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 16px;
		color: #93c5fd;
		font-size: 12px;
		margin: 0 4px 6px 0;
		cursor: pointer;
		transition: all 0.15s;
	}

	.entity-chip:hover {
		background: #334155;
		border-color: #6ee7b7;
		color: #6ee7b7;
	}
</style>
