<script lang="ts">
	import { Canvas } from '@threlte/core';
	import GraphScene from './GraphScene.svelte';

	let {
		entities = [],
		edges = [],
		onNodeClick
	}: {
		entities: Array<{
			uuid: string;
			name: string;
			node_type: string;
			summary?: string;
			labels?: string[];
		}>;
		edges: Array<{
			uuid: string;
			edge_type: string;
			source_node_uuid: string;
			target_node_uuid: string;
			fact?: string | null;
		}>;
		onNodeClick?: (uuid: string, name: string) => void;
	} = $props();
</script>

<div class="graph-container">
	<Canvas>
		<GraphScene {entities} {edges} {onNodeClick} />
	</Canvas>
</div>

<style>
	.graph-container {
		position: relative;
		width: 100%;
		height: 100%;
		min-height: 500px;
		background: radial-gradient(ellipse at center, #0f172a 0%, #020617 100%);
		border-radius: 12px;
		overflow: hidden;
	}
</style>
