<script lang="ts">
	import TraverseGraph from '$lib/components/traverse/TraverseGraph.svelte';
	import NarrativePassage from '$lib/components/traverse/NarrativePassage.svelte';
	import ChoiceCards from '$lib/components/traverse/ChoiceCards.svelte';
	import KnowledgeSynthesis from '$lib/components/traverse/KnowledgeSynthesis.svelte';
	import InnerViewPanel from '$lib/components/traverse/InnerViewPanel.svelte';
	import SessionSummary from '$lib/components/traverse/SessionSummary.svelte';

	let { data } = $props();

	let sessionId = $state<string | null>(null);
	let currentNodeId = $state<string | null>(null);
	let narrativePassage = $state<string | null>(null);
	let choiceCards = $state<
		Array<{
			text: string;
			destination_node_id: string;
			edge_weight_delta: number;
			thematic_color: string;
		}>
	>([]);
	let knowledgeSynthesis = $state<string | null>(null);
	let playerPath = $state<string[]>([]);
	let sessionState = $state<string>('idle');
	let searchQuery = $state('');
	let loading = $state(false);
	let hopData = $state<any>(null);
	let innerViewOpen = $state(false);
	let errorMessage = $state<string | null>(null);

	const suggestedQueries = [
		'quantum entanglement',
		'emergence of consciousness',
		'stellar nucleosynthesis',
		'deep ocean ecosystems',
		'artificial general intelligence'
	];

	async function handleSearch(e?: SubmitEvent) {
		e?.preventDefault();
		if (!searchQuery.trim()) return;
		loading = true;
		errorMessage = null;

		try {
			const res = await fetch('/api/traverse/enter', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ query_text: searchQuery.trim() })
			});
			if (!res.ok) {
				const err = await res.json().catch(() => ({ error: 'Gateway unavailable' }));
				errorMessage = err.error ?? 'Failed to enter the graph';
				return;
			}
			const result = await res.json();
			sessionId = result.session_id;
			currentNodeId = result.current_node_id;
			narrativePassage = result.narrative_passage;
			choiceCards = result.choice_cards ?? [];
			knowledgeSynthesis = result.knowledge_synthesis;
			playerPath = result.player_path ?? [];
			sessionState = result.state === 'terminal' ? 'terminal' : 'active';
			hopData = result;
		} catch {
			errorMessage = 'Could not connect to the gateway. Is it running?';
		} finally {
			loading = false;
		}
	}

	async function handleHop(destinationNodeId: string) {
		if (!sessionId) return;
		loading = true;
		errorMessage = null;

		try {
			const res = await fetch('/api/traverse/hop', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ session_id: sessionId, destination_node_id: destinationNodeId })
			});
			if (!res.ok) {
				const err = await res.json().catch(() => ({ error: 'Hop failed' }));
				errorMessage = err.error ?? 'Hop failed';
				return;
			}
			const result = await res.json();
			currentNodeId = result.current_node_id;
			narrativePassage = result.narrative_passage;
			choiceCards = result.choice_cards ?? [];
			knowledgeSynthesis = result.knowledge_synthesis;
			playerPath = result.player_path ?? [];
			sessionState = result.state === 'terminal' ? 'terminal' : 'active';
			hopData = result;
		} catch {
			errorMessage = 'Could not connect to the gateway.';
		} finally {
			loading = false;
		}
	}

	function resetSession() {
		sessionId = null;
		currentNodeId = null;
		narrativePassage = null;
		choiceCards = [];
		knowledgeSynthesis = null;
		playerPath = [];
		sessionState = 'idle';
		searchQuery = '';
		hopData = null;
		errorMessage = null;
	}

	function pickSuggestion(q: string) {
		searchQuery = q;
		handleSearch();
	}
</script>

<div class="traverse-page">
	<!-- Search bar -->
	<section class="search-bar">
		<form onsubmit={handleSearch} class="search-form">
			<input
				type="text"
				bind:value={searchQuery}
				placeholder="Enter a knowledge query..."
				class="search-input"
				disabled={loading}
			/>
			<button type="submit" class="search-btn" disabled={loading || !searchQuery.trim()}>
				{loading ? 'Traversing...' : 'Enter the Graph'}
			</button>
		</form>
		<button
			class="observer-toggle"
			class:active={innerViewOpen}
			onclick={() => (innerViewOpen = !innerViewOpen)}
		>
			<span class="observer-icon">⬡</span>
			Network Observer
		</button>
	</section>

	{#if errorMessage}
		<div class="error-banner">{errorMessage}</div>
	{/if}

	{#if sessionState === 'idle'}
		<!-- Landing hero -->
		<div class="hero">
			<div class="hero-content">
				<div class="hero-badge">Bittensor Subnet 42</div>
				<h1 class="hero-title">Futograph</h1>
				<p class="hero-subtitle">Navigate the living knowledge graph</p>
				<div class="suggested-queries">
					<span class="suggest-label">Try:</span>
					{#each suggestedQueries as q}
						<button class="suggest-chip" onclick={() => pickSuggestion(q)} disabled={loading}>
							{q}
						</button>
					{/each}
				</div>
			</div>
			<div class="hero-graph">
				<TraverseGraph nodes={data.nodes} edges={data.edges} playerPath={[]} currentNodeId={null} />
			</div>
		</div>
	{:else}
		<!-- Active traversal layout -->
		<div class="traversal-layout">
			<div class="main-column">
				<div class="graph-area">
					<TraverseGraph
						nodes={data.nodes}
						edges={data.edges}
						{playerPath}
						{currentNodeId}
					/>
				</div>
				<div class="narrative-area">
					{#if loading}
						<div class="skeleton">
							<div class="skeleton-line long"></div>
							<div class="skeleton-line"></div>
							<div class="skeleton-line medium"></div>
							<div class="skeleton-line long"></div>
							<div class="skeleton-line short"></div>
						</div>
					{:else if narrativePassage}
						<NarrativePassage passage={narrativePassage} />
					{/if}
				</div>
			</div>

			<div class="sidebar">
				{#if knowledgeSynthesis}
					<KnowledgeSynthesis text={knowledgeSynthesis} />
				{/if}

				{#if sessionState === 'active' && choiceCards.length > 0}
					<ChoiceCards cards={choiceCards} onSelect={handleHop} disabled={loading} />
				{:else if sessionState === 'terminal'}
					<SessionSummary
						{playerPath}
						totalWords={narrativePassage ? narrativePassage.split(/\s+/).length : 0}
						nlaStatus={hopData?.nla_agreement?.status ?? null}
						onNewTraversal={resetSession}
					/>
				{:else if loading}
					<div class="sidebar-skeleton">
						<div class="skeleton-line"></div>
						<div class="skeleton-line medium"></div>
						<div class="skeleton-line long"></div>
					</div>
				{/if}
			</div>
		</div>
	{/if}

	<InnerViewPanel open={innerViewOpen} {hopData} onClose={() => (innerViewOpen = false)} />
</div>

<style>
	.traverse-page {
		flex: 1;
		display: flex;
		flex-direction: column;
		height: calc(100vh - 65px);
		overflow: hidden;
	}

	/* ── Search bar ─────────────────────────────────────────────── */
	.search-bar {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 12px 24px;
		border-bottom: 1px solid #1e293b;
		background: #0f172a;
		flex-shrink: 0;
	}

	.search-form {
		flex: 1;
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
		transition: border-color 0.2s, box-shadow 0.2s;
	}

	.search-input:focus {
		border-color: #6ee7b7;
		box-shadow: 0 0 0 3px rgba(110, 231, 183, 0.12);
	}

	.search-input::placeholder {
		color: #64748b;
	}

	.search-input:disabled {
		opacity: 0.6;
	}

	.search-btn {
		padding: 10px 22px;
		background: #059669;
		color: white;
		border: none;
		border-radius: 8px;
		font-weight: 600;
		font-size: 14px;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.2s;
	}

	.search-btn:hover:not(:disabled) {
		background: #047857;
	}

	.search-btn:disabled {
		opacity: 0.5;
		cursor: wait;
	}

	.observer-toggle {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 14px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		color: #94a3b8;
		font-size: 13px;
		cursor: pointer;
		white-space: nowrap;
		transition: all 0.15s;
	}

	.observer-toggle:hover,
	.observer-toggle.active {
		background: #253347;
		border-color: #6ee7b7;
		color: #6ee7b7;
	}

	.observer-icon {
		font-size: 14px;
	}

	/* ── Error banner ───────────────────────────────────────────── */
	.error-banner {
		padding: 10px 24px;
		background: rgba(239, 68, 68, 0.12);
		border-bottom: 1px solid rgba(239, 68, 68, 0.3);
		color: #fca5a5;
		font-size: 13px;
		flex-shrink: 0;
	}

	/* ── Hero / landing ─────────────────────────────────────────── */
	.hero {
		flex: 1;
		display: grid;
		grid-template-rows: auto 1fr;
		overflow: hidden;
	}

	.hero-content {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		padding: 40px 24px 24px;
		gap: 12px;
	}

	.hero-badge {
		font-size: 11px;
		color: #6ee7b7;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		padding: 4px 12px;
		background: rgba(110, 231, 183, 0.08);
		border: 1px solid rgba(110, 231, 183, 0.2);
		border-radius: 20px;
	}

	.hero-title {
		font-size: 52px;
		font-weight: 800;
		letter-spacing: -0.03em;
		color: #e2e8f0;
		margin: 0;
		line-height: 1;
		background: linear-gradient(135deg, #e2e8f0 0%, #6ee7b7 100%);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
	}

	.hero-subtitle {
		font-size: 16px;
		color: #94a3b8;
		margin: 0;
	}

	.suggested-queries {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		justify-content: center;
		align-items: center;
		margin-top: 4px;
	}

	.suggest-label {
		font-size: 13px;
		color: #475569;
	}

	.suggest-chip {
		padding: 6px 14px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 20px;
		color: #93c5fd;
		font-size: 13px;
		cursor: pointer;
		transition: all 0.15s;
	}

	.suggest-chip:hover:not(:disabled) {
		background: #253347;
		border-color: #6ee7b7;
		color: #6ee7b7;
	}

	.suggest-chip:disabled {
		opacity: 0.4;
		cursor: wait;
	}

	.hero-graph {
		flex: 1;
		min-height: 0;
		padding: 0 24px 24px;
	}

	/* ── Active traversal ───────────────────────────────────────── */
	.traversal-layout {
		flex: 1;
		display: grid;
		grid-template-columns: 1fr 360px;
		min-height: 0;
		overflow: hidden;
	}

	.main-column {
		display: grid;
		grid-template-rows: 45% 55%;
		min-height: 0;
		overflow: hidden;
	}

	.graph-area {
		overflow: hidden;
		padding: 16px 16px 8px 24px;
	}

	.narrative-area {
		overflow-y: auto;
		padding: 8px 16px 16px 24px;
	}

	.sidebar {
		border-left: 1px solid #1e293b;
		background: #0f172a;
		overflow-y: auto;
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	/* ── Skeleton loading ───────────────────────────────────────── */
	.skeleton {
		padding: 24px;
		background: #0f172a;
		border-radius: 12px;
		border: 1px solid #1e293b;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.skeleton-line {
		height: 14px;
		background: linear-gradient(90deg, #1e293b 25%, #253347 50%, #1e293b 75%);
		background-size: 200% 100%;
		border-radius: 4px;
		animation: shimmer 1.5s infinite;
		width: 100%;
	}

	.skeleton-line.long {
		width: 92%;
	}

	.skeleton-line.medium {
		width: 70%;
	}

	.skeleton-line.short {
		width: 45%;
	}

	@keyframes shimmer {
		0% {
			background-position: 200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}

	.sidebar-skeleton {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 8px 0;
	}

</style>
