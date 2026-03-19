<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { eventsStore } from '$lib/stores/events.svelte';

	// ── Status badge colours ─────────────────────────────────────────────────

	const STATUS_COLOR: Record<string, string> = {
		connected: '#6ee7b7',
		connecting: '#fbbf24',
		error: '#f87171',
		closed: '#64748b',
		idle: '#64748b'
	};

	// ── Filter ───────────────────────────────────────────────────────────────

	let filterInput = $state('');
	let activeFilter = $state('');

	function applyFilter() {
		activeFilter = filterInput.trim();
		eventsStore.connect(activeFilter || undefined);
	}

	function clearFilter() {
		filterInput = '';
		activeFilter = '';
		eventsStore.connect();
	}

	// ── Derived: filtered view ───────────────────────────────────────────────

	let visibleEvents = $derived(
		activeFilter
			? eventsStore.events.filter((e) =>
					e.event_type.toLowerCase().includes(activeFilter.toLowerCase()) ||
					e.source.toLowerCase().includes(activeFilter.toLowerCase())
				)
			: eventsStore.events
	);

	// ── Lifecycle ────────────────────────────────────────────────────────────

	onMount(async () => {
		await eventsStore.loadRecent();
		eventsStore.connect();
	});

	onDestroy(() => {
		eventsStore.disconnect();
	});

	// ── Helpers ──────────────────────────────────────────────────────────────

	function formatTime(ts: number): string {
		return new Date(ts * 1000).toLocaleTimeString(undefined, {
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}

	function eventTypeColor(eventType: string): string {
		if (eventType.startsWith('validator')) return '#818cf8';
		if (eventType.startsWith('miner')) return '#34d399';
		if (eventType.startsWith('graph')) return '#fb923c';
		if (eventType.startsWith('evolution')) return '#f472b6';
		if (eventType.startsWith('session')) return '#38bdf8';
		return '#94a3b8';
	}

	function truncate(s: unknown, len: number): string {
		if (typeof s !== 'string') return '';
		return s.length > len ? s.slice(0, len) + '...' : s;
	}

	function num(v: unknown): string {
		return typeof v === 'number' ? v.toFixed(2) : '?';
	}

	function shortId(id: unknown): string {
		return typeof id === 'string' ? id.slice(0, 8) : '?';
	}

	function formatPayload(payload: Record<string, unknown>, eventType?: string): string {
		switch (eventType) {
			case 'epoch.started': {
				const uids = Array.isArray(payload.challenge_uids) ? payload.challenge_uids : [];
				return `Epoch ${payload.epoch} · ${uids.length} miners challenged · "${truncate(payload.query_text, 40)}"`;
			}
			case 'epoch.completed':
				return `Epoch ${payload.epoch} · ${payload.miners_scored} miners scored · ${typeof payload.duration_s === 'number' ? payload.duration_s.toFixed(1) : '?'}s`;
			case 'validator.scoring':
				return `Miner ${payload.uid} · traversal: ${num(payload.traversal_score)} quality: ${num(payload.quality_score)} topology: ${num(payload.topology_score)} corpus: ${num(payload.corpus_score)} weight: ${num(payload.weight)}`;
			case 'validator.weights_set': {
				const weights = typeof payload.weights === 'object' && payload.weights ? Object.keys(payload.weights) : [];
				return `Epoch ${payload.epoch} · weights set for ${weights.length} miners`;
			}
			case 'miner.query_received':
				return `${payload.synapse_type} · "${truncate(payload.query_text, 40)}"`;
			case 'miner.query_completed':
				return `${payload.synapse_type} · ${payload.chunks_returned} chunks · similarity: ${num(payload.domain_similarity)} · ${typeof payload.duration_ms === 'number' ? Math.round(payload.duration_ms) : '?'}ms`;
			case 'miner.hop_received':
				return `${payload.synapse_type} · node: ${payload.destination_node_id}`;
			case 'miner.hop_completed':
				return `${payload.synapse_type} · ${payload.passage_length_words} words · ${payload.choice_cards_count} choices · ${typeof payload.duration_ms === 'number' ? Math.round(payload.duration_ms) : '?'}ms`;
			case 'session.created':
				return `Session ${shortId(payload.session_id)} · entry: ${payload.entry_node_id} · "${truncate(payload.query_text, 40)}"`;
			case 'session.hop':
				return `Session ${shortId(payload.session_id)} · ${payload.from_node_id} → ${payload.to_node_id} · ${payload.passage_length_words} words`;
			case 'session.terminal': {
				const path = Array.isArray(payload.player_path) ? payload.player_path.join(' → ') : '?';
				return `Session ${shortId(payload.session_id)} · ${payload.total_hops} hops · path: ${path}`;
			}
			case 'system.component_started':
				return `${payload.component} started`;
			default:
				try {
					return JSON.stringify(payload, null, 2);
				} catch {
					return String(payload);
				}
		}
	}

	let expandedIds = $state<Set<string>>(new Set());

	function toggleExpand(id: string) {
		const next = new Set(expandedIds);
		if (next.has(id)) {
			next.delete(id);
		} else {
			next.add(id);
		}
		expandedIds = next;
	}
</script>

<div class="events-page">
	<!-- ── Toolbar ─────────────────────────────────────────────────────────── -->
	<section class="toolbar">
		<div class="toolbar-left">
			<span class="status-dot" style="background: {STATUS_COLOR[eventsStore.status]}"></span>
			<span class="status-label">{eventsStore.status}</span>
			<span class="event-count">{eventsStore.events.length} events</span>
		</div>

		<div class="toolbar-right">
			<form
				class="filter-form"
				onsubmit={(e) => {
					e.preventDefault();
					applyFilter();
				}}
			>
				<input
					type="text"
					bind:value={filterInput}
					placeholder="Filter by type or source..."
					class="filter-input"
				/>
				<button type="submit" class="btn btn-primary">Filter</button>
				{#if activeFilter}
					<button type="button" class="btn btn-ghost" onclick={clearFilter}>Clear</button>
				{/if}
			</form>

			<button
				class="btn btn-ghost"
				onclick={() => eventsStore.clear()}
				disabled={eventsStore.events.length === 0}
			>
				Clear log
			</button>
		</div>
	</section>

	<!-- ── Event feed ─────────────────────────────────────────────────────── -->
	<section class="feed">
		{#if eventsStore.status === 'error' && eventsStore.error}
			<div class="notice error">{eventsStore.error} — reconnecting…</div>
		{/if}

		{#if visibleEvents.length === 0}
			<div class="empty">
				{#if eventsStore.status === 'connecting'}
					Connecting to event stream…
				{:else}
					No events yet.
				{/if}
			</div>
		{:else}
			<ul class="event-list">
				{#each visibleEvents as ev (ev.correlation_id)}
					{@const expanded = expandedIds.has(ev.correlation_id)}
					<li class="event-row" class:expanded>
						<button
							class="event-summary"
							onclick={() => toggleExpand(ev.correlation_id)}
							aria-expanded={expanded}
						>
							<span class="event-time">{formatTime(ev.timestamp)}</span>
							<span class="event-type" style="color: {eventTypeColor(ev.event_type)}"
								>{ev.event_type}</span
							>
							<span class="event-source">{ev.source}</span>
							<span class="event-cid">{ev.correlation_id.slice(0, 8)}</span>
							<span class="expand-chevron">{expanded ? '▾' : '▸'}</span>
						</button>

						{#if expanded}
							<pre class="event-payload">{formatPayload(ev.payload, ev.event_type)}</pre>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</section>
</div>

<style>
	.events-page {
		flex: 1;
		display: flex;
		flex-direction: column;
		height: calc(100vh - 65px);
		overflow: hidden;
	}

	/* ── Toolbar ─────────────────────────────────────────────────────────────── */

	.toolbar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		padding: 10px 24px;
		border-bottom: 1px solid #1e293b;
		background: #0f172a;
		flex-wrap: wrap;
	}

	.toolbar-left {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.status-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.status-label {
		font-size: 13px;
		color: #94a3b8;
		text-transform: capitalize;
	}

	.event-count {
		font-size: 13px;
		color: #475569;
	}

	.toolbar-right {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.filter-form {
		display: flex;
		gap: 6px;
	}

	.filter-input {
		padding: 7px 14px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 7px;
		color: #e2e8f0;
		font-size: 13px;
		outline: none;
		width: 220px;
		transition: border-color 0.2s;
	}

	.filter-input:focus {
		border-color: #6ee7b7;
	}

	.filter-input::placeholder {
		color: #475569;
	}

	.btn {
		padding: 7px 16px;
		border-radius: 7px;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		border: 1px solid transparent;
		transition: all 0.15s;
		white-space: nowrap;
	}

	.btn-primary {
		background: #059669;
		color: white;
		border-color: #059669;
	}

	.btn-primary:hover {
		background: #047857;
	}

	.btn-ghost {
		background: transparent;
		color: #94a3b8;
		border-color: #334155;
	}

	.btn-ghost:hover {
		color: #e2e8f0;
		border-color: #6ee7b7;
		background: rgba(110, 231, 183, 0.06);
	}

	.btn:disabled {
		opacity: 0.4;
		cursor: default;
	}

	/* ── Feed ────────────────────────────────────────────────────────────────── */

	.feed {
		flex: 1;
		overflow-y: auto;
		padding: 0;
	}

	.notice {
		padding: 10px 24px;
		font-size: 13px;
	}

	.notice.error {
		background: rgba(248, 113, 113, 0.1);
		color: #f87171;
		border-bottom: 1px solid rgba(248, 113, 113, 0.2);
	}

	.empty {
		padding: 48px 24px;
		text-align: center;
		color: #475569;
		font-size: 14px;
	}

	.event-list {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.event-row {
		border-bottom: 1px solid #1e293b;
	}

	.event-row:hover {
		background: rgba(255, 255, 255, 0.02);
	}

	.event-summary {
		width: 100%;
		display: grid;
		grid-template-columns: 80px 200px 1fr 80px 16px;
		align-items: center;
		gap: 12px;
		padding: 10px 24px;
		background: transparent;
		border: none;
		color: #e2e8f0;
		font-size: 13px;
		text-align: left;
		cursor: pointer;
		font-family: inherit;
	}

	.event-time {
		color: #475569;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}

	.event-type {
		font-weight: 500;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.event-source {
		color: #94a3b8;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.event-cid {
		color: #334155;
		font-size: 11px;
		font-family: monospace;
	}

	.expand-chevron {
		color: #475569;
		font-size: 11px;
	}

	.event-payload {
		margin: 0;
		padding: 10px 24px 14px 116px;
		font-size: 12px;
		color: #94a3b8;
		background: #0a1628;
		border-top: 1px solid #1e293b;
		white-space: pre-wrap;
		word-break: break-all;
		line-height: 1.5;
	}
</style>
