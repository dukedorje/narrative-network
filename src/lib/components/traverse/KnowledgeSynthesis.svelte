<script lang="ts">
	interface Props {
		text: string;
	}

	let { text }: Props = $props();

	let collapsed = $state(false);
</script>

<div class="synthesis-panel">
	<button class="synthesis-header" onclick={() => (collapsed = !collapsed)}>
		<span class="synthesis-icon">◈</span>
		<span class="synthesis-title">Knowledge Synthesis</span>
		<span class="collapse-indicator">{collapsed ? '▸' : '▾'}</span>
	</button>
	{#if !collapsed}
		<div class="synthesis-body">
			<p class="synthesis-text">{text}</p>
		</div>
	{/if}
</div>

<style>
	.synthesis-panel {
		background: #0f172a;
		border: 1px solid #1e293b;
		border-radius: 10px;
		overflow: hidden;
		margin-bottom: 16px;
	}

	.synthesis-header {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		padding: 12px 14px;
		background: transparent;
		border: none;
		color: #94a3b8;
		cursor: pointer;
		text-align: left;
		transition: background 0.15s;
	}

	.synthesis-header:hover {
		background: #1e293b;
	}

	.synthesis-icon {
		font-size: 14px;
		color: #6ee7b7;
	}

	.synthesis-title {
		flex: 1;
		font-size: 12px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #94a3b8;
	}

	.collapse-indicator {
		font-size: 12px;
		color: #475569;
	}

	.synthesis-body {
		padding: 0 14px 14px;
	}

	.synthesis-text {
		font-size: 13px;
		line-height: 1.6;
		color: #94a3b8;
		margin: 0;
	}
</style>
