<script lang="ts">
	interface Props {
		playerPath: string[];
		totalWords: number;
		nlaStatus: string | null;
		onNewTraversal: () => void;
	}

	let { playerPath, totalWords, nlaStatus, onNewTraversal }: Props = $props();

	const totalHops = $derived((playerPath?.length ?? 1) - 1);

	function nlaStatusColor(status: string | null): string {
		if (!status) return '#64748b';
		const map: Record<string, string> = {
			draft: '#fbbf24',
			registered: '#6ee7b7',
			active: '#93c5fd',
			settled: '#a78bfa',
			disputed: '#f97316'
		};
		return map[status.toLowerCase()] ?? '#94a3b8';
	}
</script>

<div class="summary-card">
	<div class="summary-header">
		<div class="header-glow"></div>
		<h2 class="title">Journey Complete</h2>
		<p class="subtitle">Your traversal through the knowledge graph has concluded.</p>
	</div>

	<div class="stats-grid">
		<div class="stat-block">
			<span class="stat-value">{totalHops}</span>
			<span class="stat-label">Hops Taken</span>
		</div>
		<div class="stat-block">
			<span class="stat-value">{(playerPath?.length ?? 0)}</span>
			<span class="stat-label">Nodes Visited</span>
		</div>
		<div class="stat-block">
			<span class="stat-value">{totalWords.toLocaleString()}</span>
			<span class="stat-label">Words Generated</span>
		</div>
	</div>

	{#if playerPath?.length > 0}
		<div class="path-section">
			<h4 class="section-label">Path Taken</h4>
			<div class="breadcrumb">
				{#each playerPath as node, i}
					<span class="crumb">{node}</span>
					{#if i < playerPath.length - 1}
						<span class="crumb-sep">→</span>
					{/if}
				{/each}
			</div>
		</div>
	{/if}

	{#if nlaStatus}
		<div class="nla-status">
			<h4 class="section-label">Settlement Status</h4>
			<span
				class="status-badge"
				style="color: {nlaStatusColor(nlaStatus)}; border-color: {nlaStatusColor(nlaStatus)};"
			>
				{nlaStatus}
			</span>
		</div>
	{/if}

	<button class="new-traversal-btn" onclick={onNewTraversal}>
		Start New Traversal
	</button>
</div>

<style>
	.summary-card {
		position: relative;
		background: #0f172a;
		border: 1px solid #1e293b;
		border-radius: 16px;
		padding: 32px;
		max-width: 580px;
		margin: 0 auto;
		overflow: hidden;
		animation: fadeIn 0.5s ease forwards;
		box-shadow:
			0 0 0 1px #1e293b,
			0 0 40px rgba(110, 231, 183, 0.06);
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(12px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.summary-header {
		position: relative;
		margin-bottom: 28px;
		text-align: center;
	}

	.header-glow {
		position: absolute;
		top: -40px;
		left: 50%;
		transform: translateX(-50%);
		width: 200px;
		height: 100px;
		background: radial-gradient(ellipse, rgba(110, 231, 183, 0.15) 0%, transparent 70%);
		pointer-events: none;
	}

	.title {
		font-size: 26px;
		font-weight: 700;
		color: #e2e8f0;
		margin: 0 0 8px;
	}

	.subtitle {
		font-size: 14px;
		color: #64748b;
		margin: 0;
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1px;
		background: #1e293b;
		border-radius: 12px;
		overflow: hidden;
		margin-bottom: 24px;
	}

	.stat-block {
		background: #0f172a;
		padding: 16px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
	}

	.stat-value {
		font-size: 24px;
		font-weight: 700;
		color: #6ee7b7;
		font-variant-numeric: tabular-nums;
	}

	.stat-label {
		font-size: 11px;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.path-section,
	.nla-status {
		margin-bottom: 20px;
	}

	.section-label {
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #475569;
		margin: 0 0 10px;
	}

	.breadcrumb {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 4px;
		background: #1e293b;
		border-radius: 8px;
		padding: 10px 12px;
	}

	.crumb {
		font-size: 12px;
		color: #93c5fd;
		padding: 2px 6px;
		background: rgba(147, 197, 253, 0.08);
		border-radius: 4px;
	}

	.crumb-sep {
		font-size: 12px;
		color: #334155;
	}

	.status-badge {
		display: inline-block;
		padding: 3px 10px;
		border-radius: 10px;
		font-size: 12px;
		font-weight: 600;
		border: 1px solid currentColor;
		text-transform: capitalize;
	}

	.new-traversal-btn {
		display: block;
		width: 100%;
		padding: 13px;
		background: #059669;
		color: white;
		border: none;
		border-radius: 10px;
		font-size: 15px;
		font-weight: 600;
		cursor: pointer;
		transition: background 0.2s;
		margin-top: 8px;
	}

	.new-traversal-btn:hover {
		background: #047857;
	}

	.new-traversal-btn:active {
		background: #065f46;
	}
</style>
