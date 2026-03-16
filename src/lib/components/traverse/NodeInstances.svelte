<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { HTML } from '@threlte/extras';
	import { untrack } from 'svelte';
	import {
		InstancedMesh,
		SphereGeometry,
		MeshStandardMaterial,
		Object3D,
		Color
	} from 'three';
	import { createSpring, tickSpring } from '../graph/spring';

	interface NodeData {
		node_id: string;
		has_corpus: boolean;
		neighbours: string[];
	}

	interface Props {
		nodes: NodeData[];
		positions: Map<string, { x: number; y: number; z: number }>;
		currentNodeId: string | null;
		pathSet: Set<string>;
		onNodeClick?: (nodeId: string) => void;
	}

	let { nodes, positions, currentNodeId = null, pathSet, onNodeClick }: Props = $props();

	// --- Per-node animated state ---
	interface NodeAnimState {
		scale: ReturnType<typeof createSpring>;
		emissive: ReturnType<typeof createSpring>;
		opacity: ReturnType<typeof createSpring>;
	}
	let animStates = $state(new Map<string, NodeAnimState>());

	// Ensure anim states exist for all nodes
	// Use untrack to read animStates without creating a circular dependency
	$effect(() => {
		const nodeList = nodes; // reactive dependency on nodes only
		untrack(() => {
			const existing = animStates;
			const updated = new Map<string, NodeAnimState>();
			for (const node of nodeList) {
				const state = existing.get(node.node_id);
				if (state) {
					updated.set(node.node_id, state);
				} else {
					updated.set(node.node_id, {
						scale: createSpring(0, 0), // start at 0, animate in
						emissive: createSpring(0.1),
						opacity: createSpring(0.3)
					});
				}
			}
			animStates = updated;
		});
	});

	// Update spring targets when state changes
	$effect(() => {
		for (const node of nodes) {
			const state = animStates.get(node.node_id);
			if (!state) continue;

			const isCurrent = node.node_id === currentNodeId;
			const isPath = pathSet.has(node.node_id);

			state.scale.target = isCurrent ? 0.35 : isPath ? 0.25 : 0.15;
			state.emissive.target = isCurrent ? 0.8 : isPath ? 0.5 : 0.1;
			state.opacity.target = isCurrent ? 1.0 : isPath ? 0.9 : 0.5;
		}
	});

	// --- Colors ---
	function nodeColor(nodeId: string, hasCorpus: boolean): string {
		if (nodeId === currentNodeId) return '#6ee7b7';
		if (pathSet.has(nodeId)) return '#34d399';
		return hasCorpus ? '#93c5fd' : '#475569';
	}

	// --- InstancedMesh setup ---
	const MAX_INSTANCES = 256;
	const geometry = new SphereGeometry(1, 20, 14); // Unit sphere, scaled per instance
	const material = new MeshStandardMaterial({
		roughness: 0.25,
		metalness: 0.1,
		transparent: true
	});
	const dummy = new Object3D();
	const tempColor = new Color();
	let mesh: InstancedMesh | undefined = $state(undefined);

	// Shared click-target geometry (avoid per-node allocation)
	const clickGeometry = new SphereGeometry(0.5, 8, 6);

	// Tick: update springs and instance transforms
	useTask((delta) => {
		if (!mesh) return;

		const dt = Math.min(delta, 0.05); // use actual frame delta, capped
		let idx = 0;

		for (const node of nodes) {
			const pos = positions.get(node.node_id);
			const state = animStates.get(node.node_id);
			if (!pos || !state || idx >= MAX_INSTANCES) continue;

			// Tick springs
			tickSpring(state.scale, dt, 0.1);
			tickSpring(state.emissive, dt, 0.12);
			tickSpring(state.opacity, dt, 0.1);

			// Set instance transform
			const s = Math.max(state.scale.value, 0.01);
			dummy.position.set(pos.x, pos.y, pos.z);
			dummy.scale.set(s, s, s);
			dummy.updateMatrix();
			mesh.setMatrixAt(idx, dummy.matrix);

			// Set instance color (includes emissive baked in via brightness)
			const baseColor = nodeColor(node.node_id, node.has_corpus);
			tempColor.set(baseColor);
			// Brighten by emissive intensity
			const e = state.emissive.value;
			tempColor.r = Math.min(1, tempColor.r + e * 0.3);
			tempColor.g = Math.min(1, tempColor.g + e * 0.3);
			tempColor.b = Math.min(1, tempColor.b + e * 0.3);
			mesh.setColorAt(idx, tempColor);

			idx++;
		}

		mesh.count = idx;
		mesh.instanceMatrix.needsUpdate = true;
		if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
	});

	function handleClick(nodeId: string) {
		if (onNodeClick) onNodeClick(nodeId);
	}
</script>

<!-- InstancedMesh for all node spheres — single draw call -->
<T.InstancedMesh
	bind:ref={mesh}
	args={[geometry, material, MAX_INSTANCES]}
	frustumCulled={false}
/>

<!-- HTML labels (these can't be instanced, but they're lightweight) -->
{#each nodes as node (node.node_id)}
	{@const pos = positions.get(node.node_id)}
	{@const state = animStates.get(node.node_id)}
	{#if pos && state}
		<HTML
			position={[pos.x, pos.y - Math.max(state.scale.value, 0.1) - 0.35, pos.z]}
			center
			pointerEvents="none"
		>
			<span
				class="node-label"
				class:current={node.node_id === currentNodeId}
				class:path={pathSet.has(node.node_id)}
			>
				{node.node_id}
			</span>
		</HTML>

		<!-- Invisible click target (larger than visual sphere for easier clicking) -->
		<T.Mesh
			position={[pos.x, pos.y, pos.z]}
			visible={false}
			onclick={() => handleClick(node.node_id)}
			geometry={clickGeometry}
		>
			<T.MeshBasicMaterial />
		</T.Mesh>
	{/if}
{/each}

<style>
	.node-label {
		font-size: 10px;
		color: #64748b;
		white-space: nowrap;
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
		user-select: none;
		pointer-events: none;
	}

	.node-label.current {
		color: #6ee7b7;
		font-weight: 700;
		font-size: 12px;
	}

	.node-label.path {
		color: #a7f3d0;
		font-weight: 600;
	}
</style>
