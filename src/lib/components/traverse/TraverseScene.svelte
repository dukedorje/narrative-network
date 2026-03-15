<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { OrbitControls, HTML, interactivity } from '@threlte/extras';
	import { BufferGeometry, Float32BufferAttribute, Color } from 'three';
	import { ForceLayout } from '../graph/force-layout';

	interface Props {
		nodes: Array<{ node_id: string; has_corpus: boolean; neighbours: string[] }>;
		edges: Array<{ source_id: string; dest_id: string; weight: number; traversal_count: number }>;
		playerPath: string[];
		currentNodeId: string | null;
	}

	let { nodes = [], edges = [], playerPath = [], currentNodeId = null }: Props = $props();

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

	function isPathEdge(sourceId: string, destId: string): boolean {
		return pathEdgeSet.has(`${sourceId}__${destId}`);
	}

	// --- Node appearance ---
	function nodeRadius(nodeId: string): number {
		if (nodeId === currentNodeId) return 0.35;
		if (pathSet.has(nodeId)) return 0.25;
		return 0.15;
	}

	function nodeColor(nodeId: string, hasCorpus: boolean): string {
		if (nodeId === currentNodeId) return '#6ee7b7';
		if (pathSet.has(nodeId)) return '#34d399';
		return hasCorpus ? '#93c5fd' : '#475569';
	}

	function nodeEmissive(nodeId: string): number {
		if (nodeId === currentNodeId) return 0.8;
		if (pathSet.has(nodeId)) return 0.5;
		return 0.1;
	}

	// --- Force layout ---
	const layout = new ForceLayout({
		linkDistance: 5,
		linkStrength: 0.5,
		chargeStrength: -12,
		chargeDistanceMax: 25,
		centerStrength: 0.02,
		collisionPadding: 0.4,
		damping: 0.85
	});

	let nodePositions = $state<Map<string, { x: number; y: number; z: number }>>(new Map());
	let edgeGeo = $state<BufferGeometry>(new BufferGeometry());
	let pathEdgeGeo = $state<BufferGeometry>(new BufferGeometry());
	let settling = $state(true);

	// --- Update layout when data changes ---
	$effect(() => {
		const nodeData = nodes.map((n) => ({
			id: n.node_id,
			radius: nodeRadius(n.node_id)
		}));
		const nodeIds = new Set(nodes.map((n) => n.node_id));
		const linkData = edges
			.filter((e) => nodeIds.has(e.source_id) && nodeIds.has(e.dest_id))
			.map((e) => ({
				source: e.source_id,
				target: e.dest_id
			}));
		layout.setGraph(nodeData, linkData);
		settling = true;
	});

	// --- Animation loop ---
	useTask(() => {
		const ticks = settling ? 3 : 1;
		let active = false;
		for (let i = 0; i < ticks; i++) {
			active = layout.tick() || active;
		}
		settling = active;

		// Snapshot positions
		const positions = new Map<string, { x: number; y: number; z: number }>();
		for (const [id, node] of layout.nodes) {
			positions.set(id, { x: node.x, y: node.y, z: node.z });
		}
		nodePositions = positions;

		// Edge geometries — split into regular and path edges
		const regularPts: number[] = [];
		const pathPts: number[] = [];
		for (const link of layout.links) {
			const a = layout.nodes.get(link.source);
			const b = layout.nodes.get(link.target);
			if (!a || !b) continue;
			const arr = isPathEdge(link.source, link.target) ? pathPts : regularPts;
			arr.push(a.x, a.y, a.z, b.x, b.y, b.z);
		}

		const rGeo = new BufferGeometry();
		if (regularPts.length > 0) {
			rGeo.setAttribute('position', new Float32BufferAttribute(regularPts, 3));
		}
		edgeGeo = rGeo;

		const pGeo = new BufferGeometry();
		if (pathPts.length > 0) {
			pGeo.setAttribute('position', new Float32BufferAttribute(pathPts, 3));
		}
		pathEdgeGeo = pGeo;
	});
</script>

<!-- Camera -->
<T.PerspectiveCamera makeDefault position={[0, 10, 18]} fov={55}>
	<OrbitControls
		enableDamping
		dampingFactor={0.12}
		minDistance={3}
		maxDistance={50}
		maxPolarAngle={Math.PI * 0.85}
	/>
</T.PerspectiveCamera>

<!-- Lighting -->
<T.AmbientLight intensity={0.35} />
<T.DirectionalLight position={[8, 12, 8]} intensity={0.7} />
<T.DirectionalLight position={[-5, -3, -8]} intensity={0.15} />

<!-- Regular edges -->
{#if edgeGeo.attributes.position}
	<T.LineSegments geometry={edgeGeo}>
		<T.LineBasicMaterial color="#1e293b" opacity={0.5} transparent />
	</T.LineSegments>
{/if}

<!-- Path edges (glowing) -->
{#if pathEdgeGeo.attributes.position}
	<T.LineSegments geometry={pathEdgeGeo}>
		<T.LineBasicMaterial color="#6ee7b7" opacity={0.9} transparent linewidth={2} />
	</T.LineSegments>
{/if}

<!-- Nodes -->
{#each nodes as node (node.node_id)}
	{@const pos = nodePositions.get(node.node_id)}
	{@const r = nodeRadius(node.node_id)}
	{@const color = nodeColor(node.node_id, node.has_corpus)}
	{@const emissive = nodeEmissive(node.node_id)}
	{#if pos}
		<T.Mesh position={[pos.x, pos.y, pos.z]}>
			<T.SphereGeometry args={[r, 16, 12]} />
			<T.MeshStandardMaterial
				{color}
				emissive={color}
				emissiveIntensity={emissive}
				roughness={0.3}
				metalness={0.1}
				transparent
				opacity={node.node_id === currentNodeId || pathSet.has(node.node_id) ? 1.0 : 0.5}
			/>
		</T.Mesh>

		<!-- Label -->
		<HTML position={[pos.x, pos.y - r - 0.35, pos.z]} center pointerEvents="none">
			<span
				class="node-label"
				class:current={node.node_id === currentNodeId}
				class:path={pathSet.has(node.node_id)}
			>
				{node.node_id}
			</span>
		</HTML>
	{/if}
{/each}

<style>
	.node-label {
		font-size: 10px;
		color: #64748b;
		white-space: nowrap;
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
		user-select: none;
	}

	.node-label.current {
		color: #6ee7b7;
		font-weight: 700;
		font-size: 11px;
	}

	.node-label.path {
		color: #a7f3d0;
	}
</style>
