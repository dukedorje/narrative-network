<script lang="ts">
	import { fly, fade } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import TraverseGraph from '$lib/components/traverse/TraverseGraph.svelte';
	import InnerViewPanel from '$lib/components/traverse/InnerViewPanel.svelte';

	let { data } = $props();

	type ChoiceCard = {
		text: string;
		destination_node_id: string;
		edge_weight_delta: number;
		thematic_color: string;
	};

	let sessionId = $state<string | null>(null);
	let currentNodeId = $state<string | null>(null);
	let choiceCards = $state<ChoiceCard[]>([]);
	let knowledgeSynthesis = $state<string | null>(null);
	let playerPath = $state<string[]>([]);
	let sessionState = $state<string>('idle');
	let searchQuery = $state('');
	let loading = $state(false);
	let hopData = $state<any>(null);
	let innerViewOpen = $state(false);
	let errorMessage = $state<string | null>(null);
	let narrativeHistory = $state<string[]>([]);
	let narrativeAreaEl = $state<HTMLElement | null>(null);
	let pendingNodeLabel = $state<string | null>(null);

	const suggestedQueries = [
		'quantum entanglement',
		'emergence of consciousness',
		'stellar nucleosynthesis',
		'deep ocean ecosystems',
		'artificial general intelligence'
	];

	// Auto-start traversal if ?q= param is present
	$effect(() => {
		const q = page.url.searchParams.get('q');
		if (q && sessionState === 'idle' && !loading) {
			searchQuery = q;
			// Clear the query param so refresh doesn't re-trigger
			goto('/traverse', { replaceState: true, keepFocus: true });
			handleSearch();
		}
	});

	// Auto-scroll narrative area to bottom when new passages arrive or loading starts
	$effect(() => {
		if ((narrativeHistory.length > 0 || loading) && narrativeAreaEl) {
			requestAnimationFrame(() => {
				narrativeAreaEl?.scrollTo({ top: narrativeAreaEl.scrollHeight, behavior: 'smooth' });
			});
		}
	});

	async function handleSearch(e?: SubmitEvent) {
		e?.preventDefault();
		if (!searchQuery.trim()) return;
		loading = true;
		errorMessage = null;
		// Transition to traversal view immediately so user sees the loading state
		sessionState = 'loading';
		pendingNodeLabel = searchQuery.trim();

		try {
			const res = await fetch('/api/traverse/enter', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ query_text: searchQuery.trim() })
			});
			if (!res.ok) {
				const err = await res.json().catch(() => ({ error: 'Gateway unavailable' }));
				errorMessage = err.error ?? 'Failed to enter the graph';
				sessionState = 'idle';
				return;
			}
			const result = await res.json();
			sessionId = result.session_id;
			currentNodeId = result.current_node_id;
			choiceCards = result.choice_cards ?? [];
			knowledgeSynthesis = result.knowledge_synthesis;
			playerPath = result.player_path ?? [];
			sessionState = result.state === 'terminal' ? 'terminal' : 'active';
			hopData = result;
			if (result.narrative_passage) {
				narrativeHistory = [result.narrative_passage];
			}
		} catch {
			errorMessage = 'Could not connect to the gateway. Is it running?';
			sessionState = 'idle';
		} finally {
			loading = false;
			pendingNodeLabel = null;
			if (errorMessage) setTimeout(() => (errorMessage = null), 5000);
		}
	}

	async function handleHop(card: ChoiceCard) {
		if (!sessionId) return;
		loading = true;
		errorMessage = null;
		pendingNodeLabel = card.destination_node_id.replace(/-/g, ' ');

		try {
			const res = await fetch('/api/traverse/hop', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ session_id: sessionId, destination_node_id: card.destination_node_id })
			});
			if (!res.ok) {
				if (res.status === 404) {
					// Session expired or not found — silently restart
					resetSession();
					return;
				}
				const err = await res.json().catch(() => ({ error: 'Hop failed' }));
				errorMessage = err.error ?? 'Hop failed';
				return;
			}
			const result = await res.json();
			currentNodeId = result.current_node_id;
			choiceCards = result.choice_cards ?? [];
			knowledgeSynthesis = result.knowledge_synthesis;
			playerPath = result.player_path ?? [];
			sessionState = result.state === 'terminal' ? 'terminal' : 'active';
			hopData = result;
			if (result.narrative_passage) {
				narrativeHistory = [...narrativeHistory, result.narrative_passage];
			}
		} catch {
			errorMessage = 'Could not connect to the gateway.';
		} finally {
			loading = false;
			pendingNodeLabel = null;
			if (errorMessage) setTimeout(() => (errorMessage = null), 5000);
		}
	}

	function resetSession() {
		sessionId = null;
		currentNodeId = null;
		choiceCards = [];
		knowledgeSynthesis = null;
		playerPath = [];
		sessionState = 'idle';
		searchQuery = '';
		hopData = null;
		errorMessage = null;
		narrativeHistory = [];
		pendingNodeLabel = null;
	}

	function pickSuggestion(q: string) {
		searchQuery = q;
		handleSearch();
	}

	let isTerminal = $derived(
		sessionState === 'terminal' ||
			(sessionState === 'active' && !loading && choiceCards.length === 0)
	);
</script>

<div class="traverse-page">
	{#if sessionState === 'idle'}
		<!-- ── Splash / Hero ─────────────────────────────────────────── -->
		<section class="search-bar" in:fly={{ y: -20, duration: 400, easing: cubicOut }}>
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
		</section>

		{#if errorMessage}
			<div class="error-banner" in:fade={{ duration: 300 }}>{errorMessage}</div>
		{/if}

		<div class="hero">
			<div class="hero-content">
				<div class="hero-badge" in:fade={{ duration: 500, delay: 100 }}>Narrative Network</div>
				<h1 class="hero-title" in:fly={{ y: 20, duration: 500, delay: 200, easing: cubicOut }}>Futograph</h1>
				<p class="hero-subtitle" in:fly={{ y: 20, duration: 500, delay: 300, easing: cubicOut }}>Navigate the living knowledge graph</p>
				<div class="suggested-queries" in:fly={{ y: 16, duration: 500, delay: 400, easing: cubicOut }}>
					<span class="suggest-label">Try:</span>
					{#each suggestedQueries as q, i}
						<button
							class="suggest-chip"
							onclick={() => pickSuggestion(q)}
							disabled={loading}
							in:fly={{ y: 12, duration: 350, delay: 500 + i * 70, easing: cubicOut }}
						>
							{q}
						</button>
					{/each}
				</div>
			</div>
			<div class="hero-graph" in:fade={{ duration: 600, delay: 400 }}>
				<TraverseGraph nodes={data.nodes} edges={data.edges} playerPath={[]} currentNodeId={null} />
			</div>
		</div>
	{:else}
		<!-- ── Active Traversal ───────────────────────────────────────── -->
		<section class="traverse-bar">
			<div class="traverse-bar-inner">
				<span class="current-node-label">
					{#if loading && pendingNodeLabel}
						{pendingNodeLabel}
						<span class="node-label-generating">generating...</span>
					{:else}
						{currentNodeId?.replace(/-/g, ' ') ?? 'Traversing...'}
					{/if}
				</span>
				<button class="reset-btn" onclick={resetSession}>New session</button>
				<button
					class="observer-toggle"
					class:active={innerViewOpen}
					onclick={() => (innerViewOpen = !innerViewOpen)}
				>
					<span class="observer-icon">&#x2B21;</span>
					Observer
				</button>
			</div>
		</section>

		{#if errorMessage}
			<div class="error-banner">{errorMessage}</div>
		{/if}

		<section class="traverse-panel">
			<!-- Narrative area (left) -->
			<div class="narrative-area" bind:this={narrativeAreaEl}>
				{#if playerPath.length > 0}
					<div class="path-breadcrumb">
						{playerPath.map(p => p.replace(/-/g, ' ')).join(' \u2192 ')}
					</div>
				{/if}

				{#if narrativeHistory.length === 0 && !loading}
					<p class="narrative-prompt">Entering the graph...</p>
				{:else}
					<div class="narrative-passages">
						{#each narrativeHistory as passage, i (i)}
							<p
								class="narrative-passage"
								class:narrative-passage--latest={i === narrativeHistory.length - 1 && !loading}
								in:fly={{ y: 30, duration: 500, easing: cubicOut }}
							>
								{passage}
							</p>
						{/each}
					</div>
				{/if}

				{#if loading}
					<div class="narrative-generating" in:fade={{ duration: 300 }}>
						<div class="generating-header">
							<div class="generating-pulse"></div>
							<span>Generating narrative{pendingNodeLabel ? ` for ${pendingNodeLabel}` : ''}...</span>
						</div>
						<div class="generating-skeleton">
							<div class="skeleton-line" style="width: 92%"></div>
							<div class="skeleton-line" style="width: 87%; animation-delay: 0.15s"></div>
							<div class="skeleton-line" style="width: 95%; animation-delay: 0.3s"></div>
							<div class="skeleton-line" style="width: 60%; animation-delay: 0.45s"></div>
						</div>
					</div>
				{/if}

				{#if knowledgeSynthesis && !loading}
					<div class="knowledge-synthesis" in:fade={{ duration: 400, delay: 200 }}>
						<span class="synthesis-label">Synthesis</span>
						<p>{knowledgeSynthesis}</p>
					</div>
				{/if}
			</div>

			<!-- Choices area (right) -->
			<div class="choices-area">
				{#if loading}
					<h2 class="choices-heading">Where next?</h2>
					<div class="loading-state" in:fade={{ duration: 300 }}>
						<div class="spinner"></div>
						<p>Weaving the path...</p>
					</div>
				{:else if isTerminal}
					<h2 class="choices-heading">Journey complete</h2>
					<div class="terminal-state" in:fade={{ duration: 400 }}>
						<p>You have reached the end of this traversal.</p>
						<p class="terminal-path">
							{playerPath.length} nodes visited
						</p>
						{#if knowledgeSynthesis}
							<p class="terminal-synthesis">{knowledgeSynthesis}</p>
						{/if}
						<button class="enter-btn" onclick={resetSession}>Begin again</button>
					</div>
				{:else}
					<h2 class="choices-heading">Where next?</h2>
					<div class="choice-cards">
						{#each choiceCards as card, i (card.destination_node_id)}
							<button
								class="choice-card"
								style="border-left-color: {card.thematic_color};"
								onclick={() => handleHop(card)}
								in:fly={{ x: 40, duration: 400, delay: i * 80, easing: cubicOut }}
							>
								<p class="choice-text">{card.text}</p>
								<span class="choice-node">{card.destination_node_id}</span>
							</button>
						{/each}
					</div>
				{/if}
			</div>
		</section>

		<InnerViewPanel open={innerViewOpen} {hopData} onClose={() => (innerViewOpen = false)} />
	{/if}
</div>

<style>
	.traverse-page {
		flex: 1;
		display: flex;
		flex-direction: column;
		height: calc(100vh - 65px);
		overflow: hidden;
	}

	/* ── Search bar (splash mode) ──────────────────────────────────────── */
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
		letter-spacing: -0.01em;
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

	/* ── Traverse bar (active session) ─────────────────────────────── */
	.traverse-bar {
		padding: 10px 24px;
		border-bottom: 1px solid #1e293b;
		background: #0f172a;
		flex-shrink: 0;
	}

	.traverse-bar-inner {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.current-node-label {
		font-size: 14px;
		color: #6ee7b7;
		font-weight: 600;
		text-transform: capitalize;
		flex: 1;
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.node-label-generating {
		font-size: 11px;
		font-weight: 400;
		color: #64748b;
		animation: pulse-text 1.5s ease-in-out infinite;
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

	.observer-toggle {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px 12px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 6px;
		color: #94a3b8;
		font-size: 12px;
		cursor: pointer;
		transition: all 0.15s;
	}

	.observer-toggle:hover,
	.observer-toggle.active {
		background: #253347;
		border-color: #6ee7b7;
		color: #6ee7b7;
	}

	.observer-icon {
		font-size: 13px;
	}

	/* ── Traverse panel (narrative + choices) ───────────────────────── */
	.traverse-panel {
		flex: 1;
		display: grid;
		grid-template-columns: 1fr 380px;
		overflow: hidden;
	}

	/* ── Narrative area ────────────────────────────────────────────── */
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
		text-transform: capitalize;
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

	/* ── Narrative generating indicator ────────────────────────────── */
	.narrative-generating {
		margin-top: 20px;
		padding: 20px;
		background: #111f35;
		border-radius: 8px;
		border-left: 3px solid #6ee7b7;
	}

	.generating-header {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-bottom: 16px;
		color: #94a3b8;
		font-size: 13px;
		font-weight: 500;
		letter-spacing: 0.02em;
	}

	.generating-pulse {
		width: 8px;
		height: 8px;
		background: #6ee7b7;
		border-radius: 50%;
		animation: pulse-dot 1.4s ease-in-out infinite;
	}

	.generating-skeleton {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.skeleton-line {
		height: 12px;
		background: linear-gradient(
			90deg,
			#1e293b 25%,
			#253347 50%,
			#1e293b 75%
		);
		background-size: 200% 100%;
		border-radius: 6px;
		animation: shimmer 1.5s ease-in-out infinite;
	}

	@keyframes shimmer {
		0% { background-position: 200% 0; }
		100% { background-position: -200% 0; }
	}

	@keyframes pulse-dot {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.4; transform: scale(0.8); }
	}

	@keyframes pulse-text {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
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

	/* ── Choices area ──────────────────────────────────────────────── */
	.choices-area {
		padding: 28px 24px;
		background: #0a1628;
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

	/* ── Loading state ─────────────────────────────────────────────── */
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

	/* ── Choice cards ──────────────────────────────────────────────── */
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

	/* ── Terminal state ────────────────────────────────────────────── */
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

	.terminal-path {
		font-size: 13px !important;
		color: #94a3b8 !important;
	}

	.terminal-synthesis {
		color: #94a3b8 !important;
		font-style: italic;
		padding: 12px 14px;
		background: #0d1e30;
		border-radius: 8px;
		border-left: 3px solid #93c5fd;
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
		align-self: flex-start;
	}

	.enter-btn:hover {
		background: #047857;
	}
</style>
