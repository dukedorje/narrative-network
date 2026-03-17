<script lang="ts">
	import { fly, fade } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import TraverseGraph from '$lib/components/traverse/TraverseGraph.svelte';
	import InnerViewPanel from '$lib/components/traverse/InnerViewPanel.svelte';
	import ContextCard from '$lib/components/ui/ContextCard.svelte';
	import ChoiceCard from '$lib/components/ui/ChoiceCard.svelte';

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
	let graphSideOpen = $state(false);
	let errorMessage = $state<string | null>(null);
	let narrativeHistory = $state<string[]>([]);
	let narrativeAreaEl = $state<HTMLElement | null>(null);

	const suggestedQueries = [
		'quantum entanglement',
		'emergence of consciousness',
		'stellar nucleosynthesis',
		'deep ocean ecosystems',
		'artificial general intelligence'
	];

	// Auto-scroll narrative area to bottom when new passages arrive
	$effect(() => {
		if (narrativeHistory.length > 0 && narrativeAreaEl) {
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
		} finally {
			loading = false;
		}
	}

	async function handleHop(card: ChoiceCard) {
		if (!sessionId) return;
		loading = true;
		errorMessage = null;

		try {
			const res = await fetch('/api/traverse/hop', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ session_id: sessionId, destination_node_id: card.destination_node_id })
			});
			if (!res.ok) {
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
		</section>

		{#if errorMessage}
			<div class="error-banner">{errorMessage}</div>
		{/if}

		<div class="hero">
			<div class="hero-content">
				<div class="hero-badge">Narrative Network</div>
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
		<!-- ── Active Traversal ───────────────────────────────────────── -->
		<section class="traverse-bar">
			<div class="traverse-bar-inner">
				<span class="current-node-label">
					{currentNodeId?.replace(/-/g, ' ') ?? 'Traversing...'}
				</span>
				<button class="reset-btn" onclick={resetSession}>New session</button>
				<button
					class="observer-toggle"
					class:active={graphSideOpen}
					onclick={() => (graphSideOpen = !graphSideOpen)}
				>
					<span class="observer-icon">&#x25C8;</span>
					Network Graph
				</button>
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

		<div class="core-experience">
			<div class="context-column">
				<ContextCard
					nodeId={currentNodeId}
					synthesis={knowledgeSynthesis}
					narrativeHistory={narrativeHistory}
				/>
			</div>

			<div class="choices-column" class:is-terminal={isTerminal}>
				{#if loading}
					<div class="loading-state" in:fade={{ duration: 300 }}>
						<div class="spinner"></div>
						<p>Weaving the path...</p>
					</div>
				{:else if isTerminal}
					<div class="terminal-state" in:fade={{ duration: 400 }}>
						<div class="terminal-header">
							<h2>Journey Complete</h2>
							<p class="terminal-path">{playerPath.length} nodes visited</p>
						</div>
						<button class="enter-btn" onclick={resetSession}>Begin new traversal</button>
					</div>
				{:else}
					<h3 class="step-heading">Next Steps Options</h3>
					<div class="choice-grid">
						{#each choiceCards as card, i (card.destination_node_id)}
							<div class="choice-wrapper" in:fly={{ y: 20, duration: 400, delay: i * 80, easing: cubicOut }}>
								<ChoiceCard
									text={card.text}
									destinationNodeId={card.destination_node_id}
									thematicColor={card.thematic_color}
									onClick={() => handleHop(card)}
								/>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>

		<InnerViewPanel open={innerViewOpen} {hopData} onClose={() => (innerViewOpen = false)} />

		<!-- Graph Side Panel -->
		<aside class="graph-panel-side" class:panel-open={graphSideOpen}>
			<div class="graph-header">
				<span class="graph-title">Visualizer</span>
				<button class="close-btn" onclick={() => (graphSideOpen = false)}>✕</button>
			</div>
			<div class="graph-body">
				{#if graphSideOpen}
					<TraverseGraph nodes={data.nodes} edges={data.edges} playerPath={playerPath} {currentNodeId} />
				{/if}
			</div>
		</aside>
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

	/* ── Graph Side Panel ─────────────────────────────────────────── */
	.graph-panel-side {
		position: fixed;
		top: 65px;
		right: 0;
		width: 480px;
		height: calc(100vh - 65px);
		background: rgba(15, 23, 42, 0.9);
		backdrop-filter: blur(12px);
		-webkit-backdrop-filter: blur(12px);
		border-left: 1px solid #1e293b;
		display: flex;
		flex-direction: column;
		z-index: 45;
		transform: translateX(100%);
		transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
		box-shadow: -10px 0 30px rgba(0, 0, 0, 0.5);
	}

	.graph-panel-side.panel-open {
		transform: translateX(0);
	}

	.graph-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 14px 16px;
		border-bottom: 1px solid #1e293b;
		background: #0f172a;
		flex-shrink: 0;
	}

	.graph-title {
		font-size: 13px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #93c5fd;
	}

	.close-btn {
		background: none;
		border: none;
		color: #64748b;
		font-size: 14px;
		cursor: pointer;
		padding: 4px 6px;
		border-radius: 4px;
		line-height: 1;
		transition: color 0.15s, background 0.15s;
	}

	.close-btn:hover {
		color: #e2e8f0;
		background: #1e293b;
	}

	.graph-body {
		flex: 1;
		min-height: 0;
		position: relative;
	}

	/* ── Core Layout (Stripped Down) ──────────────────────────────── */
	.core-experience {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 40px 24px;
		overflow-y: auto;
		background: radial-gradient(circle at 50% -20%, #1e293b 0%, #020617 70%);
		scrollbar-width: thin;
		scrollbar-color: #334155 transparent;
	}

	.core-experience::-webkit-scrollbar {
		width: 6px;
	}

	.core-experience::-webkit-scrollbar-thumb {
		background: #334155;
		border-radius: 3px;
	}

	.context-column {
		width: 100%;
		max-width: 800px;
		margin-bottom: 24px;
	}

	.choices-column {
		width: 100%;
		max-width: 800px;
		display: flex;
		flex-direction: column;
		gap: 24px;
	}

	.step-heading {
		font-size: 16px;
		font-weight: 600;
		color: #94a3b8;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0;
		border-bottom: 1px solid rgba(51, 65, 85, 0.4);
		padding-bottom: 12px;
	}

	.choice-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
		gap: 20px;
	}

	.terminal-state {
		text-align: center;
		padding: 40px;
		background: rgba(30, 41, 59, 0.4);
		border: 1px solid rgba(51, 65, 85, 0.6);
		border-radius: 16px;
		backdrop-filter: blur(8px);
	}

	.terminal-header h2 {
		font-size: 32px;
		color: #e2e8f0;
		margin: 0 0 12px;
		letter-spacing: -0.02em;
	}

	.terminal-path {
		color: #94a3b8;
		font-size: 16px;
		margin-bottom: 32px;
	}

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
		display: inline-block;
	}

	.enter-btn:hover {
		background: #047857;
	}
</style>
