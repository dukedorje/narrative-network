<script lang="ts">
	interface Card {
		text: string;
		destination_node_id: string;
		edge_weight_delta: number;
		thematic_color: string;
	}

	interface Props {
		cards: Card[];
		onSelect: (destination_node_id: string) => void;
		disabled?: boolean;
	}

	let { cards, onSelect, disabled = false }: Props = $props();
</script>

<div class="choice-cards">
	<h3 class="section-label">Choose Your Path</h3>
	{#each cards as card}
		<button
			class="choice-card"
			style="--accent: {card.thematic_color}"
			onclick={() => onSelect(card.destination_node_id)}
			{disabled}
		>
			<span class="card-text">{card.text}</span>
			<span class="card-node">→ {card.destination_node_id}</span>
		</button>
	{/each}
</div>

<style>
	.choice-cards {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.section-label {
		font-size: 11px;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		margin: 0 0 4px;
	}

	.choice-card {
		display: flex;
		flex-direction: column;
		gap: 4px;
		padding: 14px 16px;
		background: #1e293b;
		border: 1px solid #334155;
		border-left: 3px solid var(--accent, #6ee7b7);
		border-radius: 8px;
		color: #e2e8f0;
		text-align: left;
		cursor: pointer;
		transition:
			background 0.15s,
			border-color 0.15s,
			box-shadow 0.15s;
	}

	.choice-card:hover:not(:disabled) {
		background: #253347;
		border-color: var(--accent, #6ee7b7);
		box-shadow: 0 0 12px color-mix(in srgb, var(--accent, #6ee7b7) 25%, transparent);
	}

	.choice-card:disabled {
		opacity: 0.45;
		cursor: wait;
	}

	.card-text {
		font-size: 14px;
		line-height: 1.4;
		color: #e2e8f0;
	}

	.card-node {
		font-size: 11px;
		color: #64748b;
		font-family: 'SF Mono', 'Fira Code', monospace;
	}
</style>
