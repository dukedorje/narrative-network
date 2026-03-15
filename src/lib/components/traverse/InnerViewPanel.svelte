<script lang="ts">
	import ScoringBreakdown from './ScoringBreakdown.svelte';
	import InnerViewSections from './InnerViewSections.svelte';

	interface HopData {
		scores: { traversal: number; quality: number; topology: number; corpus: number };
		emission_snapshot: { traversal: number; quality: number; topology: number; reserve: number };
		graph_delta: Record<string, { before: number; after: number }>;
		responding_nodes: Array<{ node_id: string; similarity: number }>;
		unbrowse_used: boolean;
		unbrowse_context: string | null;
		nla_agreement?: { agreement_text: string; status: string } | null;
	}

	interface Props {
		open: boolean;
		hopData: HopData | null;
		onClose?: () => void;
	}

	let { open, hopData, onClose }: Props = $props();
</script>

<aside class="panel" class:panel-open={open} aria-label="Network Observer">
	<div class="panel-header">
		<span class="panel-title">Network Observer</span>
		<button class="close-btn" onclick={onClose} aria-label="Close panel">✕</button>
	</div>

	<div class="panel-body">
		{#if hopData}
			<ScoringBreakdown scores={hopData.scores} />
			<InnerViewSections
				emission_snapshot={hopData.emission_snapshot}
				graph_delta={hopData.graph_delta}
				responding_nodes={hopData.responding_nodes}
				unbrowse_used={hopData.unbrowse_used}
				unbrowse_context={hopData.unbrowse_context}
				nla_agreement={hopData.nla_agreement}
			/>
		{:else}
			<div class="placeholder">
				<div class="placeholder-icon">◎</div>
				<p>Awaiting traversal data...</p>
			</div>
		{/if}
	</div>
</aside>

<style>
	.panel {
		position: fixed;
		top: 65px;
		right: 0;
		width: 420px;
		height: calc(100vh - 65px);
		background: #0f172a;
		border-left: 1px solid #1e293b;
		display: flex;
		flex-direction: column;
		z-index: 50;
		transform: translateX(100%);
		transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.panel-open {
		transform: translateX(0);
	}

	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 14px 16px;
		border-bottom: 1px solid #1e293b;
		flex-shrink: 0;
	}

	.panel-title {
		font-size: 13px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #6ee7b7;
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

	.panel-body {
		flex: 1;
		overflow-y: auto;
		scrollbar-width: thin;
		scrollbar-color: #334155 transparent;
	}

	.panel-body::-webkit-scrollbar {
		width: 4px;
	}

	.panel-body::-webkit-scrollbar-track {
		background: transparent;
	}

	.panel-body::-webkit-scrollbar-thumb {
		background: #334155;
		border-radius: 2px;
	}

	.placeholder {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 200px;
		gap: 12px;
	}

	.placeholder-icon {
		font-size: 28px;
		color: #334155;
		animation: pulse 2.5s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 0.4; }
		50% { opacity: 1; }
	}

	.placeholder p {
		font-size: 13px;
		color: #475569;
		margin: 0;
	}
</style>
