<script lang="ts">
	import { T, useTask } from '@threlte/core';
	import { BufferGeometry, Float32BufferAttribute } from 'three';

	interface Props {
		positions: Map<string, { x: number; y: number; z: number }>;
		links: Array<{ source: string; target: string }>;
		pathEdgeSet: Set<string>;
	}

	let { positions, links, pathEdgeSet }: Props = $props();

	// Persistent geometries and attributes — never replaced, only updated
	const regularGeo = new BufferGeometry();
	const pathGeo = new BufferGeometry();

	// Pre-allocated buffers (grow as needed, never shrink)
	let regularBuffer = new Float32Array(256);
	let pathBuffer = new Float32Array(64);
	let regularAttr: Float32BufferAttribute | null = null;
	let pathAttr: Float32BufferAttribute | null = null;
	let hasRegularData = $state(false);
	let hasPathData = $state(false);

	// Use useTask for per-frame position updates (not $effect)
	useTask(() => {
		// Count edges to check buffer capacity
		let regularCount = 0;
		let pathCount = 0;
		for (const link of links) {
			if (!positions.has(link.source) || !positions.has(link.target)) continue;
			if (
				pathEdgeSet.has(`${link.source}__${link.target}`) ||
				pathEdgeSet.has(`${link.target}__${link.source}`)
			) {
				pathCount++;
			} else {
				regularCount++;
			}
		}

		// Grow buffers if needed (reallocate attribute with new backing array)
		const regularSize = regularCount * 6;
		const pathSize = pathCount * 6;

		if (regularBuffer.length < regularSize) {
			regularBuffer = new Float32Array(Math.max(regularSize * 2, 256));
			regularAttr = null; // force re-creation
		}
		if (pathBuffer.length < pathSize) {
			pathBuffer = new Float32Array(Math.max(pathSize * 2, 64));
			pathAttr = null;
		}

		let ri = 0;
		let pi = 0;
		for (const link of links) {
			const a = positions.get(link.source);
			const b = positions.get(link.target);
			if (!a || !b) continue;

			const isPath =
				pathEdgeSet.has(`${link.source}__${link.target}`) ||
				pathEdgeSet.has(`${link.target}__${link.source}`);
			const buf = isPath ? pathBuffer : regularBuffer;
			const idx = isPath ? pi : ri;

			buf[idx] = a.x;
			buf[idx + 1] = a.y;
			buf[idx + 2] = a.z;
			buf[idx + 3] = b.x;
			buf[idx + 4] = b.y;
			buf[idx + 5] = b.z;

			if (isPath) pi += 6;
			else ri += 6;
		}

		// Update regular edges
		if (ri > 0) {
			if (!regularAttr) {
				regularAttr = new Float32BufferAttribute(regularBuffer, 3);
				regularGeo.setAttribute('position', regularAttr);
			}
			regularAttr.needsUpdate = true;
			regularGeo.setDrawRange(0, ri / 3);
			hasRegularData = true;
		} else {
			hasRegularData = false;
		}

		// Update path edges
		if (pi > 0) {
			if (!pathAttr) {
				pathAttr = new Float32BufferAttribute(pathBuffer, 3);
				pathGeo.setAttribute('position', pathAttr);
			}
			pathAttr.needsUpdate = true;
			pathGeo.setDrawRange(0, pi / 3);
			hasPathData = true;
		} else {
			hasPathData = false;
		}
	});
</script>

<!-- Regular edges -->
{#if hasRegularData}
	<T.LineSegments geometry={regularGeo}>
		<T.LineBasicMaterial color="#1e3a5f" opacity={0.4} transparent />
	</T.LineSegments>
{/if}

<!-- Path edges (glowing) -->
{#if hasPathData}
	<T.LineSegments geometry={pathGeo}>
		<T.LineBasicMaterial color="#6ee7b7" opacity={0.9} transparent />
	</T.LineSegments>
{/if}
