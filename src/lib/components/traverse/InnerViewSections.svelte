<script lang="ts">
	interface Props {
		emission_snapshot: { traversal: number; quality: number; topology: number; reserve: number };
		graph_delta: Record<string, { before: number; after: number }>;
		responding_nodes: Array<{ node_id: string; similarity: number }>;
		unbrowse_used: boolean;
		unbrowse_context: string | null;
		nla_agreement?: { agreement_text: string; status: string } | null;
	}

	let {
		emission_snapshot,
		graph_delta,
		responding_nodes,
		unbrowse_used,
		unbrowse_context,
		nla_agreement = null
	}: Props = $props();

	let unbrowseExpanded = $state(false);
	let nodesExpanded = $state(false);

	const emissionPools = $derived(() => {
		const snap = emission_snapshot ?? { traversal: 0, quality: 0, topology: 0, reserve: 0 };
		const total = snap.traversal + snap.quality + snap.topology + snap.reserve || 1;
		return [
			{ key: 'traversal', label: 'Traversal', color: '#93c5fd', value: snap.traversal, pct: (snap.traversal / total) * 100 },
			{ key: 'quality', label: 'Quality', color: '#6ee7b7', value: snap.quality, pct: (snap.quality / total) * 100 },
			{ key: 'topology', label: 'Topology', color: '#fbbf24', value: snap.topology, pct: (snap.topology / total) * 100 },
			{ key: 'reserve', label: 'Reserve', color: '#94a3b8', value: snap.reserve, pct: (snap.reserve / total) * 100 }
		];
	});

	const deltaEntries = $derived(
		Object.entries(graph_delta ?? {}).map(([edge, vals]) => ({
			edge,
			before: vals.before,
			after: vals.after,
			delta: vals.after - vals.before
		}))
	);

	const sortedNodes = $derived(
		[...(responding_nodes ?? [])].sort((a, b) => b.similarity - a.similarity)
	);

	const visibleNodes = $derived(nodesExpanded ? sortedNodes : sortedNodes.slice(0, 5));

	function nlaStatusColor(status: string): string {
		const map: Record<string, string> = {
			draft: '#fbbf24',
			registered: '#6ee7b7',
			active: '#93c5fd',
			settled: '#a78bfa',
			disputed: '#f97316'
		};
		return map[status?.toLowerCase()] ?? '#94a3b8';
	}
</script>

<div class="inner-sections">
	<!-- Emission Pools -->
	<section class="section">
		<h4 class="section-header">Emission Pools</h4>
		<div class="stacked-bar">
			{#each emissionPools() as pool}
				{#if pool.pct > 0}
					<div
						class="stack-segment"
						style="width: {pool.pct}%; background: {pool.color};"
						title="{pool.label}: {pool.pct.toFixed(1)}%"
					></div>
				{/if}
			{/each}
		</div>
		<div class="pool-legend">
			{#each emissionPools() as pool}
				<div class="legend-item">
					<span class="legend-dot" style="background: {pool.color};"></span>
					<span class="legend-label">{pool.label}</span>
					<span class="legend-pct">{pool.pct.toFixed(1)}%</span>
				</div>
			{/each}
		</div>
	</section>

	<!-- Edge Deltas -->
	<section class="section">
		<h4 class="section-header">Edge Dynamics</h4>
		{#if deltaEntries.length === 0}
			<p class="empty-text">No edge changes</p>
		{:else}
			<table class="delta-table">
				<thead>
					<tr>
						<th>Edge</th>
						<th>Before</th>
						<th>After</th>
						<th>Delta</th>
					</tr>
				</thead>
				<tbody>
					{#each deltaEntries as row}
						<tr>
							<td class="edge-name" title={row.edge}>{row.edge.length > 18 ? row.edge.slice(0, 16) + '…' : row.edge}</td>
							<td>{row.before.toFixed(3)}</td>
							<td>{row.after.toFixed(3)}</td>
							<td class:positive={row.delta > 0} class:negative={row.delta < 0}>
								{row.delta > 0 ? '+' : ''}{row.delta.toFixed(3)}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</section>

	<!-- Responding Nodes -->
	<section class="section">
		<h4 class="section-header">Responding Nodes</h4>
		{#if sortedNodes.length === 0}
			<p class="empty-text">No responding nodes</p>
		{:else}
			<div class="nodes-list">
				{#each visibleNodes as node}
					<div class="node-row">
						<span class="node-id" title={node.node_id}>{node.node_id.length > 16 ? node.node_id.slice(0, 14) + '…' : node.node_id}</span>
						<div class="similarity-bar-track">
							<div class="similarity-bar-fill" style="width: {node.similarity * 100}%;"></div>
						</div>
						<span class="similarity-val">{node.similarity.toFixed(2)}</span>
					</div>
				{/each}
				{#if sortedNodes.length > 5}
					<button class="expand-btn" onclick={() => (nodesExpanded = !nodesExpanded)}>
						{nodesExpanded ? 'Show less' : `+${sortedNodes.length - 5} more`}
					</button>
				{/if}
			</div>
		{/if}
	</section>

	<!-- Unbrowse / External Context -->
	<section class="section">
		<h4 class="section-header">External Context</h4>
		{#if unbrowse_used}
			<div class="unbrowse-used">
				<span class="badge badge-green">External Context Used</span>
				{#if unbrowse_context}
					<button class="expand-btn" onclick={() => (unbrowseExpanded = !unbrowseExpanded)}>
						{unbrowseExpanded ? 'Hide' : 'Show'} context
					</button>
					{#if unbrowseExpanded}
						<div class="unbrowse-text">{unbrowse_context}</div>
					{/if}
				{/if}
			</div>
		{:else}
			<p class="empty-text">Not triggered</p>
		{/if}
	</section>

	<!-- NLA Agreement -->
	<section class="section">
		<h4 class="section-header">Settlement Agreement</h4>
		{#if nla_agreement}
			<div class="nla-block">
				<span class="badge" style="color: {nlaStatusColor(nla_agreement.status)}; border-color: {nlaStatusColor(nla_agreement.status)};">
					{nla_agreement.status}
				</span>
				<pre class="agreement-text">{nla_agreement.agreement_text}</pre>
			</div>
		{:else}
			<p class="empty-text">No agreement</p>
		{/if}
	</section>
</div>

<style>
	.inner-sections {
		display: flex;
		flex-direction: column;
	}

	.section {
		padding: 14px 16px;
		border-bottom: 1px solid #1e293b;
	}

	.section:last-child {
		border-bottom: none;
	}

	.section-header {
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #64748b;
		margin: 0 0 10px;
	}

	.empty-text {
		font-size: 12px;
		color: #475569;
		margin: 0;
	}

	/* Emission stacked bar */
	.stacked-bar {
		display: flex;
		height: 10px;
		border-radius: 5px;
		overflow: hidden;
		background: #1e293b;
		margin-bottom: 10px;
	}

	.stack-segment {
		height: 100%;
		transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.pool-legend {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 4px 8px;
	}

	.legend-item {
		display: flex;
		align-items: center;
		gap: 5px;
	}

	.legend-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.legend-label {
		font-size: 11px;
		color: #94a3b8;
		flex: 1;
	}

	.legend-pct {
		font-size: 11px;
		color: #64748b;
		font-variant-numeric: tabular-nums;
	}

	/* Delta table */
	.delta-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 11px;
	}

	.delta-table th {
		text-align: left;
		color: #475569;
		padding: 0 4px 6px;
		font-weight: 500;
		border-bottom: 1px solid #1e293b;
	}

	.delta-table td {
		padding: 4px;
		color: #94a3b8;
		font-variant-numeric: tabular-nums;
	}

	.delta-table td.edge-name {
		color: #e2e8f0;
		max-width: 100px;
	}

	.delta-table td.positive {
		color: #6ee7b7;
	}

	.delta-table td.negative {
		color: #f97316;
	}

	/* Responding nodes */
	.nodes-list {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.node-row {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.node-id {
		font-size: 11px;
		color: #93c5fd;
		width: 110px;
		flex-shrink: 0;
		font-family: monospace;
	}

	.similarity-bar-track {
		flex: 1;
		height: 4px;
		background: #1e293b;
		border-radius: 2px;
		overflow: hidden;
	}

	.similarity-bar-fill {
		height: 100%;
		background: #6ee7b7;
		border-radius: 2px;
		transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.similarity-val {
		font-size: 11px;
		color: #64748b;
		width: 32px;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}

	.expand-btn {
		background: none;
		border: none;
		color: #6ee7b7;
		font-size: 11px;
		cursor: pointer;
		padding: 2px 0;
		text-align: left;
		transition: color 0.15s;
	}

	.expand-btn:hover {
		color: #a7f3d0;
	}

	/* Unbrowse */
	.unbrowse-used {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.unbrowse-text {
		font-size: 11px;
		color: #94a3b8;
		background: #1e293b;
		border-radius: 6px;
		padding: 8px 10px;
		line-height: 1.5;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.badge {
		display: inline-block;
		padding: 2px 8px;
		border-radius: 10px;
		font-size: 11px;
		font-weight: 600;
		border: 1px solid currentColor;
		width: fit-content;
	}

	.badge-green {
		color: #6ee7b7;
		border-color: #6ee7b7;
	}

	/* NLA */
	.nla-block {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.agreement-text {
		font-size: 11px;
		color: #94a3b8;
		background: #1e293b;
		border-radius: 6px;
		padding: 8px 10px;
		line-height: 1.5;
		white-space: pre-wrap;
		word-break: break-word;
		font-family: 'Courier New', monospace;
		margin: 0;
		max-height: 140px;
		overflow-y: auto;
	}
</style>
