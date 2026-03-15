<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { OrbitControls, HTML, interactivity } from '@threlte/extras';
	import { BufferGeometry, Float32BufferAttribute, Color, Vector3 } from 'three';
	import { ForceLayout, type LayoutNode } from './force-layout';

	interface Entity {
		uuid: string;
		name: string;
		node_type: string;
		summary?: string;
		labels?: string[];
	}

	interface Edge {
		uuid: string;
		edge_type: string;
		source_node_uuid: string;
		target_node_uuid: string;
		fact?: string | null;
	}

	let {
		entities = [],
		edges = [],
		onNodeClick
	}: {
		entities: Entity[];
		edges: Edge[];
		onNodeClick?: (uuid: string, name: string) => void;
	} = $props();

	interactivity();

	// --- Color mapping ---
	const labelColors: Record<string, string> = {
		Entity: '#6ee7b7',
		TaxonomyLabel: '#93c5fd',
		Episodic: '#fbbf24',
		episode: '#f97316'
	};
	const defaultColor = '#a78bfa';

	function nodeColor(entity: Entity): string {
		if (entity.labels?.length) {
			for (const label of entity.labels) {
				if (labelColors[label]) return labelColors[label];
			}
		}
		return labelColors[entity.node_type] ?? defaultColor;
	}

	function nodeRadius(name: string): number {
		return 0.15 + Math.min(name.length * 0.008, 0.2);
	}

	// --- Force layout ---
	const layout = new ForceLayout({
		linkDistance: 4,
		linkStrength: 0.6,
		chargeStrength: -8,
		chargeDistanceMax: 20,
		centerStrength: 0.02,
		collisionPadding: 0.3,
		damping: 0.85
	});

	// Reactive state for rendering — snapshot from layout each frame
	let nodePositions = $state<Map<string, { x: number; y: number; z: number }>>(new Map());
	let edgeGeometry = $state<BufferGeometry>(new BufferGeometry());
	let hoveredNode = $state<string | null>(null);
	let settling = $state(true);

	// --- Update layout when data changes ---
	$effect(() => {
		const nodeData = entities.map((e) => ({
			id: e.uuid,
			radius: nodeRadius(e.name)
		}));
		const linkData = edges
			.filter((e) => {
				const ids = new Set(entities.map((n) => n.uuid));
				return ids.has(e.source_node_uuid) && ids.has(e.target_node_uuid);
			})
			.map((e) => ({
				source: e.source_node_uuid,
				target: e.target_node_uuid
			}));
		layout.setGraph(nodeData, linkData);
		settling = true;
	});

	// --- Animation loop: tick the simulation ---
	useTask((delta) => {
		// Run multiple ticks per frame for faster convergence
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

		// Update edge geometry
		updateEdgeGeometry();
	});

	function updateEdgeGeometry() {
		const points: number[] = [];
		for (const link of layout.links) {
			const a = layout.nodes.get(link.source);
			const b = layout.nodes.get(link.target);
			if (!a || !b) continue;
			points.push(a.x, a.y, a.z, b.x, b.y, b.z);
		}
		const geo = new BufferGeometry();
		if (points.length > 0) {
			geo.setAttribute('position', new Float32BufferAttribute(points, 3));
		}
		edgeGeometry = geo;
	}

	function handleNodeClick(entity: Entity) {
		onNodeClick?.(entity.uuid, entity.name);
	}

	function truncateLabel(name: string): string {
		if (name.length > 20) return name.slice(0, 18) + '...';
		return name;
	}
</script>

<!-- Camera -->
<T.PerspectiveCamera makeDefault position={[0, 8, 20]} fov={60}>
	<OrbitControls
		enableDamping
		dampingFactor={0.12}
		minDistance={3}
		maxDistance={60}
		maxPolarAngle={Math.PI * 0.85}
	/>
</T.PerspectiveCamera>

<!-- Ambient + directional light -->
<T.AmbientLight intensity={0.4} />
<T.DirectionalLight position={[10, 15, 10]} intensity={0.8} />
<T.DirectionalLight position={[-5, -5, -10]} intensity={0.2} />

<!-- Edge lines -->
{#if edgeGeometry.attributes.position}
	<T.LineSegments geometry={edgeGeometry}>
		<T.LineBasicMaterial color="#475569" opacity={0.4} transparent />
	</T.LineSegments>
{/if}

<!-- Nodes -->
{#each entities as entity (entity.uuid)}
	{@const pos = nodePositions.get(entity.uuid)}
	{@const r = nodeRadius(entity.name)}
	{@const color = nodeColor(entity)}
	{@const isHovered = hoveredNode === entity.uuid}
	{#if pos}
		<T.Mesh
			position={[pos.x, pos.y, pos.z]}
			onclick={() => handleNodeClick(entity)}
			onpointerenter={() => (hoveredNode = entity.uuid)}
			onpointerleave={() => {
				if (hoveredNode === entity.uuid) hoveredNode = null;
			}}
		>
			<T.SphereGeometry args={[isHovered ? r * 1.2 : r, 16, 12]} />
			<T.MeshStandardMaterial
				color={color}
				emissive={color}
				emissiveIntensity={isHovered ? 0.6 : 0.15}
				roughness={0.4}
				metalness={0.1}
				transparent
				opacity={isHovered ? 1.0 : 0.85}
			/>
		</T.Mesh>

		<!-- Label -->
		{#if entity.name.length <= 30}
			<HTML position={[pos.x, pos.y - r - 0.4, pos.z]} center pointerEvents="none">
				<span class="node-label">{truncateLabel(entity.name)}</span>
			</HTML>
		{/if}

		<!-- Hover tooltip -->
		{#if isHovered}
			<HTML position={[pos.x, pos.y + r + 0.6, pos.z]} center pointerEvents="none">
				<div class="tooltip">
					<strong>{entity.name}</strong>
					{#if entity.summary}
						<p>{entity.summary.slice(0, 200)}{entity.summary.length > 200 ? '...' : ''}</p>
					{/if}
					{#if entity.labels?.length}
						<span class="labels">{entity.labels.join(', ')}</span>
					{/if}
				</div>
			</HTML>
		{/if}
	{/if}
{/each}

<style>
	.node-label {
		font-size: 10px;
		color: #94a3b8;
		white-space: nowrap;
		text-shadow: 0 1px 3px rgba(0, 0, 0, 0.8);
		user-select: none;
	}

	.tooltip {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		padding: 10px 14px;
		font-size: 13px;
		color: #e2e8f0;
		max-width: 320px;
		white-space: normal;
		pointer-events: none;
	}

	.tooltip p {
		margin: 6px 0 0;
		font-size: 12px;
		color: #94a3b8;
		line-height: 1.4;
	}

	.tooltip .labels {
		display: block;
		margin-top: 4px;
		font-size: 11px;
		color: #6ee7b7;
	}
</style>
