<script lang="ts">
	import { T, useTask, useThrelte } from '@threlte/core';
	import { OrbitControls, HTML, interactivity } from '@threlte/extras';
	import { BufferGeometry, Float32BufferAttribute, Plane, Raycaster, Vector2, Vector3 } from 'three';
	import { ForceLayout } from './force-layout';

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

	// ─── Single source of truth for positions ───────────────────────────
	// Both nodes and edges read from this. Updated once per frame in useTask.
	// Keyed by node ID → {x, y, z}.
	let positions = new Map<string, { x: number; y: number; z: number }>();

	// Edge topology: pairs of node IDs. Rebuilt only when graph structure changes.
	let edgeRefs: Array<{ sourceId: string; targetId: string }> = [];

	// ─── Force layout ───────────────────────────────────────────────────
	const layout = new ForceLayout({
		linkDistance: 4,
		linkStrength: 0.4,
		chargeStrength: -12,
		chargeDistanceMax: 25,
		centerStrength: 0.02,
		collisionPadding: 0.3,
		damping: 0.88
	});

	// Persistent edge geometry — buffer grows as needed, never recreated per frame
	const edgeGeo = new BufferGeometry();
	let edgeBuffer = new Float32Array(512);
	let edgeAttr: Float32BufferAttribute | null = null;
	let hasEdgeData = $state(false);

	// Svelte-visible position state (triggers template re-render for node meshes)
	let nodePositions = $state<Map<string, { x: number; y: number; z: number }>>(new Map());
	let hoveredNode = $state<string | null>(null);
	let hoverTimeout: ReturnType<typeof setTimeout> | null = null;
	let settling = $state(true);

	function setHovered(id: string | null) {
		if (hoverTimeout) clearTimeout(hoverTimeout);
		if (id) {
			hoveredNode = id;
		} else {
			hoverTimeout = setTimeout(() => (hoveredNode = null), 150);
		}
	}

	// ─── Rebuild topology when data changes ─────────────────────────────
	$effect(() => {
		const nodeData = entities.map((e) => ({
			id: e.uuid,
			radius: nodeRadius(e.name)
		}));
		const nodeIds = new Set(entities.map((n) => n.uuid));

		// Edge refs: just pairs of IDs. This is the structural definition.
		edgeRefs = edges
			.filter((e) => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid))
			.map((e) => ({ sourceId: e.source_node_uuid, targetId: e.target_node_uuid }));

		const linkData = edgeRefs.map((e) => ({
			source: e.sourceId,
			target: e.targetId,
			weight: 1
		}));

		layout.setGraph(nodeData, linkData);
		settling = true;
	});

	// ─── Frame loop ─────────────────────────────────────────────────────
	// Single place where ALL position data is read and written.
	useTask(() => {
		const ticks = settling ? 3 : 1;
		let active = false;
		for (let i = 0; i < ticks; i++) {
			active = layout.tick() || active;
		}
		settling = active;

		// Step 1: Read positions from layout into our single source of truth.
		positions = new Map();
		for (const [id, node] of layout.nodes) {
			if (isFinite(node.x) && isFinite(node.y) && isFinite(node.z)) {
				positions.set(id, { x: node.x, y: node.y, z: node.z });
			}
		}

		// Step 2: Write edge geometry by looking up BOTH endpoints from `positions`.
		// An edge line endpoint IS the position of the referenced node — same object.
		let idx = 0;
		for (const edge of edgeRefs) {
			const a = positions.get(edge.sourceId);
			const b = positions.get(edge.targetId);
			if (!a || !b) continue; // skip if either node has no valid position

			const needed = idx + 6;
			if (edgeBuffer.length < needed) {
				const bigger = new Float32Array(Math.max(needed * 2, 512));
				bigger.set(edgeBuffer);
				edgeBuffer = bigger;
				edgeAttr = null; // force re-creation with new backing array
			}

			edgeBuffer[idx] = a.x;
			edgeBuffer[idx + 1] = a.y;
			edgeBuffer[idx + 2] = a.z;
			edgeBuffer[idx + 3] = b.x;
			edgeBuffer[idx + 4] = b.y;
			edgeBuffer[idx + 5] = b.z;
			idx += 6;
		}

		if (idx > 0) {
			// Create attribute from exact slice so bounding sphere doesn't see NaN/zero padding
			edgeAttr = new Float32BufferAttribute(edgeBuffer.slice(0, idx), 3);
			edgeGeo.setAttribute('position', edgeAttr);
			hasEdgeData = true;
		} else {
			hasEdgeData = false;
		}

		// Step 3: Publish positions to Svelte state so node meshes update.
		// This MUST happen AFTER edge geometry is written, so both use the same data.
		nodePositions = positions;
	});

	// ─── Drag interaction ───────────────────────────────────────────────
	const { camera, renderer } = useThrelte();
	let dragId = $state<string | null>(null);
	const dragPlane = new Plane();
	const raycaster = new Raycaster();
	const pointer = new Vector2();
	const intersection = new Vector3();
	// Track drag velocity for momentum on release
	let prevDragPos = { x: 0, y: 0, z: 0 };
	let dragVelocity = { x: 0, y: 0, z: 0 };

	function handlePointerDown(entity: Entity, event: { nativeEvent: PointerEvent }) {
		const pos = positions.get(entity.uuid);
		if (!pos) return;
		const nodePos = new Vector3(pos.x, pos.y, pos.z);
		const camDir = new Vector3();
		camera.current.getWorldDirection(camDir);
		dragPlane.setFromNormalAndCoplanarPoint(camDir, nodePos);
		dragId = entity.uuid;
		prevDragPos = { x: pos.x, y: pos.y, z: pos.z };
		dragVelocity = { x: 0, y: 0, z: 0 };
		layout.pin(entity.uuid, pos.x, pos.y, pos.z);
		layout.reheat(2);
	}

	function handlePointerMove(event: PointerEvent) {
		if (!dragId) return;
		const rect = renderer.domElement.getBoundingClientRect();
		pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
		pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
		raycaster.setFromCamera(pointer, camera.current);
		if (raycaster.ray.intersectPlane(dragPlane, intersection)) {
			// Smooth velocity tracking with exponential moving average
			const smooth = 0.3;
			dragVelocity.x = smooth * (intersection.x - prevDragPos.x) + (1 - smooth) * dragVelocity.x;
			dragVelocity.y = smooth * (intersection.y - prevDragPos.y) + (1 - smooth) * dragVelocity.y;
			dragVelocity.z = smooth * (intersection.z - prevDragPos.z) + (1 - smooth) * dragVelocity.z;
			prevDragPos = { x: intersection.x, y: intersection.y, z: intersection.z };
			layout.pin(dragId, intersection.x, intersection.y, intersection.z);
		}
	}

	function handlePointerUp() {
		if (dragId) {
			// Transfer drag momentum to the node for natural release
			layout.releaseWithVelocity(dragId, dragVelocity.x, dragVelocity.y, dragVelocity.z);
			layout.reheat(3);
			dragId = null;
		}
	}

	$effect(() => {
		if (typeof window === 'undefined') return;
		window.addEventListener('pointermove', handlePointerMove);
		window.addEventListener('pointerup', handlePointerUp);
		return () => {
			window.removeEventListener('pointermove', handlePointerMove);
			window.removeEventListener('pointerup', handlePointerUp);
		};
	});

	function handleNodeClick(entity: Entity) {
		if (dragId) return;
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

<!-- Lighting -->
<T.AmbientLight intensity={0.4} />
<T.DirectionalLight position={[10, 15, 10]} intensity={0.8} />
<T.DirectionalLight position={[-5, -5, -10]} intensity={0.2} />

<!-- Edge lines — geometry is written from the same `positions` map as nodes -->
{#if hasEdgeData}
	<T.LineSegments geometry={edgeGeo}>
		<T.LineBasicMaterial color="#475569" opacity={0.4} transparent />
	</T.LineSegments>
{/if}

<!-- Nodes — position read from `nodePositions` (same data as edge endpoints) -->
{#each entities as entity (entity.uuid)}
	{@const pos = nodePositions.get(entity.uuid)}
	{@const r = nodeRadius(entity.name)}
	{@const color = nodeColor(entity)}
	{@const isHovered = hoveredNode === entity.uuid}
	{#if pos}
		<T.Mesh
			position={[pos.x, pos.y, pos.z]}
			scale={isHovered ? 1.2 : 1}
			onclick={() => handleNodeClick(entity)}
			onpointerdown={(e: { nativeEvent: PointerEvent }) => handlePointerDown(entity, e)}
			onpointerenter={() => setHovered(entity.uuid)}
			onpointerleave={() => setHovered(null)}
		>
			<T.SphereGeometry args={[r, 16, 12]} />
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

		{#if entity.name.length <= 30}
			<HTML position={[pos.x, pos.y - r - 0.4, pos.z]} center pointerEvents="none">
				<span class="node-label">{truncateLabel(entity.name)}</span>
			</HTML>
		{/if}
	{/if}
{/each}

<!-- Single hover tooltip — rendered once, only when a node is hovered -->
{#if hoveredNode}
	{@const hoveredEntity = entities.find((e) => e.uuid === hoveredNode)}
	{@const hPos = nodePositions.get(hoveredNode)}
	{#if hoveredEntity && hPos}
		{@const hR = nodeRadius(hoveredEntity.name)}
		<HTML position={[hPos.x, hPos.y + hR + 1.2, hPos.z]} center pointerEvents="none">
			<div class="tooltip">
				<strong>{hoveredEntity.name}</strong>
				{#if hoveredEntity.summary}
					<p>
						{hoveredEntity.summary.slice(0, 200)}{hoveredEntity.summary.length > 200
							? '...'
							: ''}
					</p>
				{/if}
				{#if hoveredEntity.labels?.length}
					<span class="labels">{hoveredEntity.labels.join(', ')}</span>
				{/if}
			</div>
		</HTML>
	{/if}
{/if}

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
		transition: opacity 0.15s;
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
