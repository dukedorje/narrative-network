<script lang="ts">
	import { onMount } from 'svelte';
	import VanillaTilt from 'vanilla-tilt';

	interface Props {
		text: string;
		destinationNodeId: string;
		thematicColor: string;
		onClick: () => void;
	}

	let { text, destinationNodeId, thematicColor, onClick }: Props = $props();

	let cardEl: HTMLButtonElement;

	onMount(() => {
		VanillaTilt.init(cardEl, {
			max: 4,
			speed: 400,
			scale: 1.02,
			glare: true,
			'max-glare': 0.15,
			perspective: 1000
		});

		return () => {
			if (cardEl && (cardEl as any).vanillaTilt) {
				(cardEl as any).vanillaTilt.destroy();
			}
		};
	});
</script>

<button
	bind:this={cardEl}
	class="choice-card group"
	style="--thematic-color: {thematicColor};"
	onclick={onClick}
>
	<div class="card-glow"></div>
	<div class="card-content">
		<div class="destination-badge">
			<span>{destinationNodeId.replace(/-/g, ' ')}</span>
		</div>
		<p class="choice-text">{text}</p>
	</div>
	<div class="arrow-icon">
		<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
			<path d="M5 12H19M19 12L12 5M19 12L12 19" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
		</svg>
	</div>
</button>

<style>
	.choice-card {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: space-between;
		text-align: left;
		background: rgba(30, 41, 59, 0.4);
		backdrop-filter: blur(8px);
		-webkit-backdrop-filter: blur(8px);
		border: 1px solid rgba(51, 65, 85, 0.6);
		border-radius: 16px;
		padding: 24px;
		cursor: pointer;
		overflow: hidden;
		transition: border-color 0.3s cubic-bezier(0.4, 0, 0.2, 1), background-color 0.3s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.3s;
		width: 100%;
		gap: 20px;
		/* Prevent transform conflict with vanilla-tilt */
		transform-style: preserve-3d;
	}

	.card-glow {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: radial-gradient(
			circle at 0% 50%,
			color-mix(in srgb, var(--thematic-color) 15%, transparent),
			transparent 60%
		);
		opacity: 0;
		transition: opacity 0.3s ease;
		pointer-events: none;
	}

	.choice-card:hover {
		background: rgba(30, 41, 59, 0.6);
		border-color: color-mix(in srgb, var(--thematic-color) 40%, rgba(51, 65, 85, 0.8));
		box-shadow: 0 12px 24px -8px rgba(0, 0, 0, 0.5),
			0 0 16px -4px color-mix(in srgb, var(--thematic-color) 20%, transparent);
	}

	.choice-card:hover .card-glow {
		opacity: 1;
	}

	.card-content {
		position: relative;
		z-index: 10;
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 12px;
		transform: translateZ(20px);
	}

	.destination-badge {
		align-self: flex-start;
		padding: 4px 10px;
		background: rgba(15, 23, 42, 0.5);
		border: 1px solid color-mix(in srgb, var(--thematic-color) 30%, transparent);
		border-radius: 6px;
		font-size: 11px;
		font-weight: 500;
		font-family: var(--font-mono);
		color: color-mix(in srgb, var(--thematic-color) 90%, white);
		text-transform: capitalize;
		letter-spacing: 0.08em;
	}

	.choice-text {
		color: #f1f5f9;
		font-size: 16px;
		line-height: 1.6;
		margin: 0;
		font-weight: 400;
		letter-spacing: 0.01em;
	}

	.arrow-icon {
		position: relative;
		z-index: 1;
		color: #64748b;
		width: 40px;
		height: 40px;
		border-radius: 50%;
		background: rgba(15, 23, 42, 0.4);
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		transition: all 0.3s ease;
		border: 1px solid rgba(51, 65, 85, 0.4);
	}

	.choice-card:hover .arrow-icon {
		color: var(--thematic-color);
		background: color-mix(in srgb, var(--thematic-color) 15%, rgba(15, 23, 42, 0.8));
		border-color: color-mix(in srgb, var(--thematic-color) 30%, transparent);
		transform: translateX(4px);
	}

	/* Responsive */
	@media (max-width: 768px) {
		.choice-card {
			padding: 20px 16px;
			gap: 12px;
		}

		.choice-text {
			font-size: 15px;
		}

		.arrow-icon {
			width: 32px;
			height: 32px;
		}
	}
</style>
