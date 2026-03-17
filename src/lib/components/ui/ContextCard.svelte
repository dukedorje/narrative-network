<script lang="ts">
	import { fade, fly } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';

	interface Props {
		nodeId?: string | null;
		synthesis?: string | null;
		narrativeHistory?: string[];
	}

	let { nodeId, synthesis, narrativeHistory = [] }: Props = $props();

	// Auto-scroll logic if needed could be passed from parent or handled here
</script>

<div class="context-card" in:fade={{ duration: 400 }}>
	{#if nodeId}
		<div class="context-header">
			<span class="location-badge">Current Position</span>
			<h2 class="node-title">{nodeId.replace(/-/g, ' ')}</h2>
		</div>
	{/if}

	<div class="context-content">
		{#if narrativeHistory.length === 0}
			<p class="empty-state">Entering the graph...</p>
		{:else}
			<div class="narrative-stream">
				{#each narrativeHistory as passage, i (i)}
					<!-- Stagger animation based on array length, so older passages fade in first/faster than newest -->
					<p
						class="passage"
						class:latest={i === narrativeHistory.length - 1}
						in:fly={{ y: 20, duration: 600, delay: i * 150, easing: cubicOut }}
					>
						{passage}
					</p>
				{/each}
			</div>
		{/if}

		{#if synthesis}
			<div class="synthesis-panel" in:fade={{ duration: 400, delay: 200 }}>
				<div class="synthesis-indicator">
					<div class="pulse-dot"></div>
					<span class="label">Relative Context</span>
				</div>
				<p class="synthesis-text">{synthesis}</p>
			</div>
		{/if}
	</div>
</div>

<style>
	.context-card {
		background: rgba(15, 23, 42, 0.6);
		backdrop-filter: blur(16px);
		-webkit-backdrop-filter: blur(16px);
		border: 1px solid rgba(51, 65, 85, 0.5);
		border-radius: 16px;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
		margin-bottom: 24px;
	}

	.context-header {
		padding: 24px 32px 20px;
		border-bottom: 1px solid rgba(51, 65, 85, 0.4);
		background: linear-gradient(to bottom, rgba(30, 41, 59, 0.4), transparent);
	}

	.location-badge {
		font-size: 11px;
		color: #6ee7b7;
		text-transform: uppercase;
		letter-spacing: 0.2em;
		font-weight: 600;
		display: inline-block;
		margin-bottom: 8px;
		padding: 4px 10px;
		background: rgba(110, 231, 183, 0.1);
		border-radius: 20px;
	}

	.node-title {
		font-family: var(--font-display);
		font-size: 28px;
		font-weight: 600;
		color: #f8fafc;
		margin: 0;
		text-transform: capitalize;
		letter-spacing: -0.02em;
	}

	.context-content {
		padding: 32px;
		display: flex;
		flex-direction: column;
		gap: 32px;
	}

	.empty-state {
		color: #64748b;
		font-style: italic;
		text-align: center;
		padding: 40px 0;
	}

	.narrative-stream {
		display: flex;
		flex-direction: column;
		gap: 24px;
	}

	.passage {
		color: #cbd5e1;
		font-size: 16px;
		line-height: 1.85;
		letter-spacing: 0.01em;
		font-weight: 400;
		margin: 0;
		transition: opacity 0.3s;
		opacity: 0.7;
	}

	.passage.latest {
		opacity: 1;
		color: #f8fafc;
	}

	.synthesis-panel {
		background: rgba(13, 148, 136, 0.04);
		border-left: 3px solid #14b8a6;
		padding: 20px 24px;
		border-radius: 0 12px 12px 0;
		position: relative;
	}

	.synthesis-indicator {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 12px;
	}

	.pulse-dot {
		width: 8px;
		height: 8px;
		background: #14b8a6;
		border-radius: 50%;
		box-shadow: 0 0 12px #14b8a6;
		animation: pulse 2s infinite;
	}

	@keyframes pulse {
		0% { opacity: 0.6; transform: scale(0.9); }
		50% { opacity: 1; transform: scale(1.1); }
		100% { opacity: 0.6; transform: scale(0.9); }
	}

	.label {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.15em;
		font-weight: 600;
		color: #14b8a6;
	}

	.synthesis-text {
		color: #94a3b8;
		font-size: 15px;
		line-height: 1.65;
		margin: 0;
		font-style: italic;
		letter-spacing: 0.01em;
	}

	/* Responsive */
	@media (max-width: 768px) {
		.context-header {
			padding: 16px 20px 12px;
		}
		
		.node-title {
			font-size: 24px;
		}

		.context-content {
			padding: 20px;
			gap: 20px;
		}

		.passage {
			font-size: 15px;
			line-height: 1.7;
		}
	}
</style>
