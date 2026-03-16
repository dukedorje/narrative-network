<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { interactivity } from '@threlte/extras';
	import { ForceLayout } from '../graph/force-layout';
	import CameraController from './CameraController.svelte';
	import NodeInstances from './NodeInstances.svelte';
	import EdgeLines from './EdgeLines.svelte';

	interface Props {
		nodes: Array<{ node_id: string; has_corpus: boolean; neighbours: string[] }>;
		edges: Array<{
			source_id: string;
			dest_id: string;
			weight: number;
			traversal_count: number;
		}>;
		playerPath: string[];
		currentNodeId: string | null;
		onNodeClick?: (nodeId: string) => void;
	}

	let {
		nodes: rawNodes = [],
		edges: rawEdges = [],
		playerPath = [],
		currentNodeId = null,
		onNodeClick
	}: Props = $props();

	// Ensure arrays even if gateway returns wrapped objects
	let nodes = $derived(Array.isArray(rawNodes) ? rawNodes : []);
	let edges = $derived(Array.isArray(rawEdges) ? rawEdges : []);

	interactivity();

	// --- Derived sets ---
	let pathSet = $derived(new Set(playerPath));
	let pathEdgeSet = $derived(
		(() => {
			const s = new Set<string>();
			for (let i = 0; i < playerPath.length - 1; i++) {
				s.add(`${playerPath[i]}__${playerPath[i + 1]}`);
				s.add(`${playerPath[i + 1]}__${playerPath[i]}`);
			}
			return s;
		})()
	);

	// --- Force layout ---
	const layout = new ForceLayout({
		linkDistance: 5,
		linkStrength: 0.3,
		chargeStrength: -12,
		chargeDistanceMax: 30,
		centerStrength: 0.012,
		collisionPadding: 0.4,
		damping: 0.75,
		energyMin: 0.01,
		theta: 0.8
	});

	let nodePositions = $state<Map<string, { x: number; y: number; z: number }>>(new Map());
	let layoutLinks = $state<Array<{ source: string; target: string }>>([]);
	let settling = $state(true);

	// Track previous currentNodeId for localized reheat
	let prevNodeId: string | null = null;

	// Track previous graph identity to avoid unnecessary setGraph calls
	let prevGraphKey = '';

	// --- Update layout when graph structure changes (not on currentNodeId change) ---
	$effect(() => {
		const nodeIds = new Set(nodes.map((n) => n.node_id));
		const graphKey = [...nodeIds].sort().join(',') + '|' + edges.length;

		const nodeData = nodes.map((n) => ({
			id: n.node_id,
			radius: 0.2 // uniform radius — visual sizing handled by the mesh
		}));
		const linkData = edges
			.filter((e) => nodeIds.has(e.source_id) && nodeIds.has(e.dest_id))
			.map((e) => ({
				source: e.source_id,
				target: e.dest_id,
				weight: e.weight ?? 1
			}));

		if (graphKey !== prevGraphKey) {
			layout.setGraph(nodeData, linkData);
			prevGraphKey = graphKey;
		}
		layoutLinks = linkData;
		settling = true;
	});

	// Gentle reheat when navigating to a new node (no full graph reset)
	$effect(() => {
		if (currentNodeId && currentNodeId !== prevNodeId && prevNodeId !== null) {
			layout.reheatLocal(currentNodeId, 2, 0.5);
		}
		prevNodeId = currentNodeId;
	});

	// --- Camera focus position ---
	let focusPosition = $derived.by(() => {
		if (!currentNodeId) return null;
		const pos = nodePositions.get(currentNodeId);
		return pos ?? null;
	});
	let cameraMode = $derived<'overview' | 'focus'>(currentNodeId ? 'focus' : 'overview');

	// --- Animation loop ---
	useTask(() => {
		const ticks = settling ? 3 : 1;
		let active = false;
		for (let i = 0; i < ticks; i++) {
			active = layout.tick() || active;
		}
		settling = active;

		// Snapshot positions (skip NaN nodes)
		const positions = new Map<string, { x: number; y: number; z: number }>();
		for (const [id, node] of layout.nodes) {
			if (isFinite(node.x) && isFinite(node.y) && isFinite(node.z)) {
				positions.set(id, { x: node.x, y: node.y, z: node.z });
			}
		}
		nodePositions = positions;
	});
</script>

<!-- Camera with spring-based fly-to -->
<CameraController {focusPosition} mode={cameraMode} />

<!-- Lighting -->
<T.AmbientLight intensity={0.4} />
<T.DirectionalLight position={[8, 12, 8]} intensity={0.7} />
<T.DirectionalLight position={[-5, -3, -8]} intensity={0.2} color="#93c5fd" />

<!-- Edges -->
<EdgeLines positions={nodePositions} links={layoutLinks} {pathEdgeSet} />

<!-- Nodes (instanced) -->
<NodeInstances {nodes} positions={nodePositions} {currentNodeId} {pathSet} {onNodeClick} />
