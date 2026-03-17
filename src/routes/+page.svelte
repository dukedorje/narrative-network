<script lang="ts">
	import { fly, fade } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	import { goto } from '$app/navigation';

	let searchQuery = $state('');
	let loading = $state(false);

	const suggestedQueries = [
		{ label: 'quantum entanglement', color: '#6ee7b7' },
		{ label: 'emergence of consciousness', color: '#93c5fd' },
		{ label: 'stellar nucleosynthesis', color: '#fbbf24' },
		{ label: 'deep ocean ecosystems', color: '#67e8f9' },
		{ label: 'artificial general intelligence', color: '#c084fc' },
		{ label: 'the history of cryptography', color: '#f472b6' },
		{ label: 'symbiotic relationships in nature', color: '#86efac' },
		{ label: 'time dilation near black holes', color: '#a5b4fc' }
	];

	function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!searchQuery.trim()) return;
		goto(`/traverse?q=${encodeURIComponent(searchQuery.trim())}`);
	}

	function pickSuggestion(label: string) {
		goto(`/traverse?q=${encodeURIComponent(label)}`);
	}
</script>

<div class="splash">
	<section class="hero" in:fade={{ duration: 500 }}>
		<div class="hero-badge">Bittensor Subnet 42</div>
		<h1 class="hero-title">Narrative Network</h1>
		<p class="hero-subtitle">Navigate a living knowledge graph. Miners compete to narrate your journey.</p>
	</section>

	<section class="action-zone" in:fly={{ y: 20, duration: 500, delay: 150, easing: cubicOut }}>
		<form onsubmit={handleSubmit} class="search-form">
			<input
				type="text"
				bind:value={searchQuery}
				placeholder="Ask anything — enter the graph..."
				class="search-input"
			/>
			<button type="submit" class="search-btn" disabled={!searchQuery.trim()}>
				Enter the Graph
			</button>
		</form>

		<div class="suggestions">
			<span class="suggest-label">Try something:</span>
			<div class="suggest-grid">
				{#each suggestedQueries as { label, color }, i}
					<button
						class="suggest-chip"
						style="--chip-color: {color};"
						onclick={() => pickSuggestion(label)}
						in:fly={{ y: 16, duration: 350, delay: 250 + i * 60, easing: cubicOut }}
					>
						{label}
					</button>
				{/each}
			</div>
		</div>
	</section>

	<section class="secondary-actions" in:fade={{ duration: 400, delay: 800 }}>
		<a href="/explore" class="secondary-link">
			<span class="secondary-icon">&#x25C7;</span>
			<span>
				<strong>Explore the Graph</strong>
				<small>Search entities, visualize connections</small>
			</span>
		</a>
		<a href="/traverse" class="secondary-link">
			<span class="secondary-icon">&#x25C8;</span>
			<span>
				<strong>Open Traverse</strong>
				<small>Start a freeform traversal session</small>
			</span>
		</a>
	</section>
</div>

<style>
	.splash {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		overflow-y: auto;
		scroll-behavior: smooth;
	}

	/* ── Hero ──────────────────────────────────────────────────────────── */

	.hero {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		padding: 72px 24px 32px;
		gap: 14px;
	}

	.hero-badge {
		font-size: 11px;
		color: #6ee7b7;
		text-transform: uppercase;
		letter-spacing: 0.14em;
		padding: 5px 14px;
		background: rgba(110, 231, 183, 0.08);
		border: 1px solid rgba(110, 231, 183, 0.2);
		border-radius: 20px;
	}

	.hero-title {
		font-size: 60px;
		font-weight: 800;
		letter-spacing: -0.03em;
		margin: 0;
		line-height: 1.05;
		background: linear-gradient(135deg, #e2e8f0 0%, #6ee7b7 100%);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
	}

	.hero-subtitle {
		font-size: 17px;
		color: #94a3b8;
		margin: 0;
		max-width: 480px;
		line-height: 1.5;
	}

	/* ── Action zone ───────────────────────────────────────────────────── */

	.action-zone {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 32px;
		padding: 16px 24px 48px;
		max-width: 720px;
		width: 100%;
	}

	.search-form {
		display: flex;
		gap: 8px;
		width: 100%;
	}

	.search-input {
		flex: 1;
		padding: 14px 20px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 10px;
		color: #e2e8f0;
		font-size: 16px;
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

	.search-btn {
		padding: 14px 28px;
		background: #059669;
		color: white;
		border: none;
		border-radius: 10px;
		font-weight: 600;
		font-size: 15px;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.2s, transform 0.15s;
	}

	.search-btn:hover:not(:disabled) {
		background: #047857;
		transform: translateY(-1px);
	}

	.search-btn:disabled {
		opacity: 0.4;
		cursor: default;
	}

	/* ── Suggestions ───────────────────────────────────────────────────── */

	.suggestions {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 14px;
	}

	.suggest-label {
		font-size: 14px;
		color: #475569;
		font-weight: 500;
	}

	.suggest-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		justify-content: center;
		max-width: 640px;
	}

	.suggest-chip {
		padding: 10px 20px;
		background: rgba(30, 41, 59, 0.8);
		border: 1px solid #334155;
		border-radius: 24px;
		color: var(--chip-color, #93c5fd);
		font-size: 14px;
		cursor: pointer;
		transition: all 0.18s ease-out;
		font-weight: 500;
	}

	.suggest-chip:hover {
		background: rgba(30, 41, 59, 1);
		border-color: var(--chip-color, #6ee7b7);
		transform: translateY(-2px);
		box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
	}

	/* ── Secondary actions ─────────────────────────────────────────────── */

	.secondary-actions {
		display: flex;
		gap: 16px;
		padding: 24px 24px 80px;
		flex-wrap: wrap;
		justify-content: center;
	}

	.secondary-link {
		display: flex;
		align-items: center;
		gap: 14px;
		padding: 18px 24px;
		background: #0f172a;
		border: 1px solid #1e293b;
		border-radius: 12px;
		text-decoration: none;
		color: #e2e8f0;
		transition: border-color 0.2s, background 0.2s, transform 0.15s;
		min-width: 260px;
	}

	.secondary-link:hover {
		border-color: #334155;
		background: #111c32;
		transform: translateY(-1px);
	}

	.secondary-icon {
		font-size: 24px;
		color: #6ee7b7;
		flex-shrink: 0;
	}

	.secondary-link strong {
		display: block;
		font-size: 15px;
		font-weight: 600;
		color: #e2e8f0;
	}

	.secondary-link small {
		display: block;
		font-size: 13px;
		color: #64748b;
		margin-top: 2px;
	}
</style>
