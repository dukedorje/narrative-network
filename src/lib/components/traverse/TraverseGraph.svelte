<script lang="ts">
	import { Canvas } from '@threlte/core';
	import TraverseScene from './TraverseScene.svelte';

	interface Props {
		nodes: Array<{ node_id: string; has_corpus: boolean; neighbours: string[] }>;
		edges: Array<{ source_id: string; dest_id: string; weight: number; traversal_count: number }>;
		playerPath: string[];
		currentNodeId: string | null;
	}

	let { nodes = [], edges = [], playerPath = [], currentNodeId = null }: Props = $props();
</script>

<div class="graph-container">
	<Canvas>
		<TraverseScene {nodes} {edges} {playerPath} {currentNodeId} />
	</Canvas>
</div>

<style>
	.graph-container {
		position: relative;
		width: 100%;
		height: 100%;
		min-height: 300px;
		background: radial-gradient(ellipse at center, #0f172a 0%, #020617 100%);
		border-radius: 12px;
		overflow: hidden;
	}
</style>
