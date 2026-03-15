<script lang="ts">
	interface Props {
		scores: { traversal: number; quality: number; topology: number; corpus: number };
	}

	let { scores }: Props = $props();

	const axes = $derived([
		{ key: 'traversal', label: 'Traversal', color: '#93c5fd', value: scores?.traversal ?? 0 },
		{ key: 'quality', label: 'Quality', color: '#6ee7b7', value: scores?.quality ?? 0 },
		{ key: 'topology', label: 'Topology', color: '#fbbf24', value: scores?.topology ?? 0 },
		{ key: 'corpus', label: 'Corpus', color: '#94a3b8', value: scores?.corpus ?? 0 }
	]);
</script>

<div class="scoring-breakdown">
	<h4 class="section-header">Scoring Axes</h4>
	<div class="axes">
		{#each axes as axis}
			<div class="axis-row">
				<div class="axis-meta">
					<span class="axis-label">{axis.label}</span>
					<span class="axis-value">{axis.value.toFixed(2)}</span>
				</div>
				<div class="bar-track">
					<div
						class="bar-fill"
						style="width: {Math.min(axis.value * 100, 100)}%; background: {axis.color};"
					></div>
				</div>
			</div>
		{/each}
	</div>
</div>

<style>
	.scoring-breakdown {
		padding: 14px 16px;
		border-bottom: 1px solid #1e293b;
	}

	.section-header {
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #64748b;
		margin: 0 0 12px;
	}

	.axes {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.axis-row {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.axis-meta {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.axis-label {
		font-size: 12px;
		color: #94a3b8;
	}

	.axis-value {
		font-size: 12px;
		font-variant-numeric: tabular-nums;
		color: #e2e8f0;
		font-weight: 500;
	}

	.bar-track {
		height: 6px;
		background: #1e293b;
		border-radius: 3px;
		overflow: hidden;
	}

	.bar-fill {
		height: 100%;
		border-radius: 3px;
		transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
		min-width: 2px;
	}
</style>
