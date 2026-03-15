<script lang="ts">
	interface Props {
		passage: string;
	}

	let { passage }: Props = $props();
</script>

<div class="narrative-passage">
	<p class="passage-text">{passage}</p>
</div>

<style>
	.narrative-passage {
		padding: 24px;
		background: #0f172a;
		border-radius: 12px;
		border: 1px solid #1e293b;
		animation: fadeIn 0.4s ease-in-out;
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
			transform: translateY(8px);
		}
		to {
			opacity: 1;
			transform: translateY(0);
		}
	}

	.passage-text {
		font-size: 16px;
		line-height: 1.75;
		color: #e2e8f0;
		margin: 0;
		max-width: 72ch;
		font-family: Georgia, 'Times New Roman', serif;
		letter-spacing: 0.01em;
		white-space: pre-wrap;
	}
</style>
