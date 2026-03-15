<script lang="ts">
	import GraphCanvas from '$lib/components/graph/GraphCanvas.svelte';

	let { data } = $props();

	// ── Explore mode state ──────────────────────────────────────────────────

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

	// ── Traverse mode types ─────────────────────────────────────────────────

	type ChoiceCard = {
		text: string;
		destination_node_id: string;
		edge_weight_delta: number;
		thematic_color: string;
	};

	type TraverseSession = {
		session_id: string;
		current_node_id: string | null;
		narrative_passage: string | null;
		choice_cards: ChoiceCard[] | null;
		knowledge_synthesis: string | null;
		player_path: string[];
		state: string;
		error?: string | null;
	};

	// ── Traverse mode state ─────────────────────────────────────────────────

	let mode = $state<'explore' | 'traverse'>('explore');
	let traverseQuery = $state('');
	let traverseSession = $state<TraverseSession | null>(null);
	let traverseLoading = $state(false);
	let traverseError = $state<string | null>(null);
	let narrativeHistory = $state<string[]>([]);

	async function handleEnter(e: SubmitEvent) {
		e.preventDefault();
		if (!traverseQuery.trim()) return;
		traverseLoading = true;
		traverseError = null;

		try {
			const res = await fetch('/api/traverse/enter', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ query_text: traverseQuery, top_k_entry: 3 })
			});
			const result = await res.json();
			if (result.error) {
				traverseError = result.error;
			} else {
				traverseSession = result as TraverseSession;
				if (result.narrative_passage) {
					narrativeHistory = [...narrativeHistory, result.narrative_passage];
				}
			}
		} catch (err) {
			traverseError = 'Failed to connect to the gateway.';
			console.error('Enter failed:', err);
		} finally {
			traverseLoading = false;
		}
	}

	async function handleHop(card: ChoiceCard) {
		if (!traverseSession) return;
		traverseLoading = true;
		traverseError = null;

		try {
			const res = await fetch('/api/traverse/hop', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					session_id: traverseSession.session_id,
					destination_node_id: card.destination_node_id
				})
			});
			const result = await res.json();
			if (result.error) {
				traverseError = result.error;
			} else {
				traverseSession = result as TraverseSession;
				if (result.narrative_passage) {
					narrativeHistory = [...narrativeHistory, result.narrative_passage];
				}
			}
		} catch (err) {
			traverseError = 'Failed to connect to the gateway.';
			console.error('Hop failed:', err);
		} finally {
			traverseLoading = false;
		}
	}

	function resetTraverse() {
		traverseSession = null;
		traverseQuery = '';
		traverseError = null;
		narrativeHistory = [];
	}

	let isTerminal = $derived(
		traverseSession !== null &&
			!traverseLoading &&
			(!traverseSession.choice_cards || traverseSession.choice_cards.length === 0)
	);
</script>

<div class="explorer">
	<!-- ── Search / mode panel ──────────────────────────────────────────── -->
	<section class="search-panel">
		<div class="panel-inner">
			<div class="mode-toggle">
				<button
					class="mode-btn"
					class:active={mode === 'explore'}
					onclick={() => (mode = 'explore')}
				>
					Explore
				</button>
				<button
					class="mode-btn"
					class:active={mode === 'traverse'}
					onclick={() => (mode = 'traverse')}
				>
					Traverse
				</button>
			</div>

			{#if mode === 'explore'}
				<form onsubmit={handleSearch} class="search-form">
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
			{:else if traverseSession}
				<div class="traverse-status">
					<span class="current-node-label">
						{traverseSession.current_node_id ?? 'Traversing...'}
					</span>
					<button class="reset-btn" onclick={resetTraverse}>New session</button>
				</div>
			{/if}
		</div>
	</section>

	{#if mode === 'explore'}
		<!-- ── Explore: graph + sidebar ──────────────────────────────────── -->
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
	{:else}
		<!-- ── Traverse: narrative + choices ─────────────────────────────── -->
		<section class="traverse-panel">
			<!-- Narrative area (left) -->
			<div class="narrative-area">
				{#if traverseSession && traverseSession.player_path.length > 0}
					<div class="path-breadcrumb">
						{traverseSession.player_path.join(' → ')}
					</div>
				{/if}

				{#if narrativeHistory.length === 0}
					<p class="narrative-prompt">
						Enter a query to begin traversing the knowledge graph.
					</p>
				{:else}
					<div class="narrative-passages">
						{#each narrativeHistory as passage, i}
							<p
								class="narrative-passage"
								class:narrative-passage--latest={i === narrativeHistory.length - 1}
							>
								{passage}
							</p>
						{/each}
					</div>
				{/if}

				{#if traverseSession?.knowledge_synthesis}
					<div class="knowledge-synthesis">
						<span class="synthesis-label">Synthesis</span>
						<p>{traverseSession.knowledge_synthesis}</p>
					</div>
				{/if}
			</div>

			<!-- Choices area (right) -->
			<div class="choices-area">
				{#if !traverseSession}
					<h2 class="choices-heading">Begin your journey</h2>
					<form onsubmit={handleEnter} class="entry-form">
						<textarea
							bind:value={traverseQuery}
							placeholder="What draws you to this network?"
							class="entry-textarea"
							rows="4"
						></textarea>
						{#if traverseError}
							<p class="traverse-error">{traverseError}</p>
						{/if}
						<button type="submit" class="enter-btn" disabled={traverseLoading}>
							{traverseLoading ? 'Entering...' : 'Enter'}
						</button>
					</form>
				{:else if traverseLoading}
					<h2 class="choices-heading">Where next?</h2>
					<div class="loading-state">
						<div class="spinner"></div>
						<p>Weaving the path...</p>
					</div>
				{:else if isTerminal}
					<h2 class="choices-heading">Journey complete</h2>
					<div class="terminal-state">
						<p>You have reached the end of this traversal.</p>
						{#if traverseSession.knowledge_synthesis}
							<p class="terminal-synthesis">{traverseSession.knowledge_synthesis}</p>
						{/if}
						<button class="enter-btn" onclick={resetTraverse}>Begin again</button>
					</div>
				{:else}
					<h2 class="choices-heading">Where next?</h2>
					{#if traverseError}
						<p class="traverse-error">{traverseError}</p>
					{/if}
					<div class="choice-cards">
						{#each traverseSession.choice_cards ?? [] as card}
							<button
								class="choice-card"
								style="border-left-color: {card.thematic_color};"
								onclick={() => handleHop(card)}
							>
								<p class="choice-text">{card.text}</p>
								<span class="choice-node">{card.destination_node_id}</span>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		</section>
	{/if}
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

	/* ── Search panel ──────────────────────────────────────────────────────── */

	.search-panel {
		grid-column: 1 / -1;
		padding: 12px 24px;
		border-bottom: 1px solid #1e293b;
		background: #0f172a;
	}

	.panel-inner {
		display: flex;
		align-items: center;
		gap: 16px;
		flex-wrap: wrap;
	}

	/* ── Mode toggle ───────────────────────────────────────────────────────── */

	.mode-toggle {
		display: flex;
		gap: 4px;
		background: #1e293b;
		border-radius: 10px;
		padding: 3px;
		flex-shrink: 0;
	}

	.mode-btn {
		padding: 7px 18px;
		border-radius: 8px;
		border: none;
		background: transparent;
		color: #64748b;
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
		transition:
			background 0.18s,
			color 0.18s;
	}

	.mode-btn.active {
		background: #059669;
		color: #fff;
	}

	.mode-btn:not(.active):hover {
		color: #94a3b8;
		background: #273549;
	}

	/* ── Explore search form ───────────────────────────────────────────────── */

	.search-form {
		display: flex;
		gap: 8px;
		flex: 1;
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
		white-space: nowrap;
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
		font-size: 13px;
		color: #64748b;
	}

	/* ── Traverse status (when session active) ─────────────────────────────── */

	.traverse-status {
		display: flex;
		align-items: center;
		gap: 12px;
		flex: 1;
	}

	.current-node-label {
		font-size: 13px;
		color: #6ee7b7;
		font-weight: 500;
	}

	.reset-btn {
		padding: 6px 14px;
		background: transparent;
		border: 1px solid #334155;
		border-radius: 6px;
		color: #64748b;
		font-size: 12px;
		cursor: pointer;
		transition: all 0.15s;
	}

	.reset-btn:hover {
		border-color: #6ee7b7;
		color: #6ee7b7;
	}

	/* ── Explore mode panels ───────────────────────────────────────────────── */

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

	/* ── Traverse panel ────────────────────────────────────────────────────── */

	.traverse-panel {
		grid-column: 1 / -1;
		display: grid;
		grid-template-columns: 1fr 380px;
		overflow: hidden;
	}

	/* ── Narrative area ────────────────────────────────────────────────────── */

	.narrative-area {
		padding: 32px 40px;
		overflow-y: auto;
		background: #0f172a;
		border-right: 1px solid #1e293b;
	}

	.path-breadcrumb {
		font-size: 12px;
		color: #64748b;
		margin-bottom: 24px;
		line-height: 1.5;
		letter-spacing: 0.02em;
	}

	.narrative-prompt {
		color: #475569;
		font-size: 15px;
		line-height: 1.7;
		font-style: italic;
		margin-top: 40px;
		text-align: center;
	}

	.narrative-passages {
		display: flex;
		flex-direction: column;
		gap: 20px;
	}

	.narrative-passage {
		color: #cbd5e1;
		font-size: 15px;
		line-height: 1.8;
		margin: 0;
		padding: 16px 20px;
		background: #111f35;
		border-radius: 8px;
		border-left: 3px solid transparent;
		transition: border-color 0.2s;
	}

	.narrative-passage--latest {
		color: #e2e8f0;
		border-left-color: #6ee7b7;
		background: #142035;
	}

	.knowledge-synthesis {
		margin-top: 32px;
		padding: 16px 20px;
		background: #0d1e30;
		border: 1px solid #1e3a5f;
		border-radius: 8px;
	}

	.synthesis-label {
		font-size: 11px;
		color: #93c5fd;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 600;
		display: block;
		margin-bottom: 8px;
	}

	.knowledge-synthesis p {
		color: #94a3b8;
		font-size: 14px;
		line-height: 1.6;
		margin: 0;
		font-style: italic;
	}

	/* ── Choices area ──────────────────────────────────────────────────────── */

	.choices-area {
		padding: 28px 24px;
		background: #0a1628;
		border-left: 1px solid #1e293b;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.choices-heading {
		font-size: 15px;
		font-weight: 700;
		color: #94a3b8;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		margin: 0;
	}

	/* ── Entry form ────────────────────────────────────────────────────────── */

	.entry-form {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.entry-textarea {
		width: 100%;
		padding: 12px 14px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		color: #e2e8f0;
		font-size: 14px;
		line-height: 1.6;
		resize: vertical;
		outline: none;
		font-family: inherit;
		transition: border-color 0.2s;
		box-sizing: border-box;
	}

	.entry-textarea:focus {
		border-color: #6ee7b7;
	}

	.entry-textarea::placeholder {
		color: #64748b;
	}

	.enter-btn {
		padding: 11px 20px;
		background: #059669;
		color: white;
		border: none;
		border-radius: 8px;
		font-size: 14px;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.2s;
		align-self: flex-end;
	}

	.enter-btn:hover {
		background: #047857;
	}

	.enter-btn:disabled {
		opacity: 0.5;
		cursor: wait;
	}

	.traverse-error {
		font-size: 13px;
		color: #f87171;
		margin: 0;
		padding: 10px 14px;
		background: #1f0f0f;
		border-radius: 6px;
		border-left: 3px solid #f87171;
	}

	/* ── Loading state ─────────────────────────────────────────────────────── */

	.loading-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 16px;
		padding: 32px 0;
		color: #64748b;
		font-size: 14px;
	}

	.spinner {
		width: 28px;
		height: 28px;
		border: 2px solid #1e293b;
		border-top-color: #6ee7b7;
		border-radius: 50%;
		animation: spin 0.7s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* ── Choice cards ──────────────────────────────────────────────────────── */

	.choice-cards {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.choice-card {
		background: #1e293b;
		border: 1px solid #334155;
		border-left: 4px solid #6ee7b7;
		border-radius: 10px;
		padding: 16px;
		cursor: pointer;
		text-align: left;
		transition:
			transform 0.15s ease-out,
			border-color 0.15s,
			background 0.15s;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.choice-card:hover {
		transform: translateY(-2px);
		background: #253348;
		border-color: #4b6480;
	}

	.choice-text {
		color: #cbd5e1;
		font-size: 14px;
		line-height: 1.55;
		margin: 0;
	}

	.choice-node {
		font-size: 11px;
		color: #64748b;
		font-family: 'JetBrains Mono', monospace;
		letter-spacing: 0.02em;
	}

	/* ── Terminal state ────────────────────────────────────────────────────── */

	.terminal-state {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.terminal-state p {
		color: #64748b;
		font-size: 14px;
		line-height: 1.6;
		margin: 0;
	}

	.terminal-synthesis {
		color: #94a3b8 !important;
		font-style: italic;
		padding: 12px 14px;
		background: #0d1e30;
		border-radius: 8px;
		border-left: 3px solid #93c5fd;
	}
</style>
