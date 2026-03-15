/**
 * Barnes-Hut octree for O(n log n) force approximation.
 * Replaces O(n²) brute-force charge calculation in the force layout.
 */

export interface OctreeBody {
	x: number;
	y: number;
	z: number;
	mass: number;
	/** Reference back to the source node (opaque to the octree). */
	id: string;
}

interface OctreeNode {
	// Bounding box
	cx: number;
	cy: number;
	cz: number;
	halfSize: number;

	// Center of mass
	comX: number;
	comY: number;
	comZ: number;
	totalMass: number;

	body: OctreeBody | null; // Leaf: single body
	children: (OctreeNode | null)[] | null; // Internal: 8 children (octants)
}

function createNode(cx: number, cy: number, cz: number, halfSize: number): OctreeNode {
	return {
		cx,
		cy,
		cz,
		halfSize,
		comX: 0,
		comY: 0,
		comZ: 0,
		totalMass: 0,
		body: null,
		children: null
	};
}

/** Get octant index (0-7) for a point relative to the node center. */
function octantIndex(node: OctreeNode, x: number, y: number, z: number): number {
	let idx = 0;
	if (x >= node.cx) idx |= 1;
	if (y >= node.cy) idx |= 2;
	if (z >= node.cz) idx |= 4;
	return idx;
}

function childCenter(
	node: OctreeNode,
	octant: number
): { cx: number; cy: number; cz: number; halfSize: number } {
	const qs = node.halfSize * 0.5;
	return {
		cx: node.cx + (octant & 1 ? qs : -qs),
		cy: node.cy + (octant & 2 ? qs : -qs),
		cz: node.cz + (octant & 4 ? qs : -qs),
		halfSize: qs
	};
}

function insertBody(node: OctreeNode, body: OctreeBody, depth: number): void {
	// Prevent infinite recursion for overlapping points
	if (depth > 40) return;

	if (node.body === null && node.children === null) {
		// Empty leaf — place body here
		node.body = body;
		return;
	}

	if (node.body !== null) {
		// Leaf with existing body — subdivide
		const existing = node.body;
		node.body = null;
		node.children = [null, null, null, null, null, null, null, null];

		// Re-insert existing body
		const oi = octantIndex(node, existing.x, existing.y, existing.z);
		const cc = childCenter(node, oi);
		node.children[oi] = createNode(cc.cx, cc.cy, cc.cz, cc.halfSize);
		insertBody(node.children[oi]!, existing, depth + 1);
	}

	// Insert new body into appropriate child
	if (!node.children) {
		node.children = [null, null, null, null, null, null, null, null];
	}
	const oi = octantIndex(node, body.x, body.y, body.z);
	if (!node.children[oi]) {
		const cc = childCenter(node, oi);
		node.children[oi] = createNode(cc.cx, cc.cy, cc.cz, cc.halfSize);
	}
	insertBody(node.children[oi]!, body, depth + 1);
}

/** Recursively compute center of mass for each node. */
function computeCOM(node: OctreeNode): void {
	if (node.body !== null) {
		node.comX = node.body.x;
		node.comY = node.body.y;
		node.comZ = node.body.z;
		node.totalMass = node.body.mass;
		return;
	}

	if (!node.children) return;

	let mx = 0,
		my = 0,
		mz = 0,
		mt = 0;
	for (const child of node.children) {
		if (child) {
			computeCOM(child);
			mx += child.comX * child.totalMass;
			my += child.comY * child.totalMass;
			mz += child.comZ * child.totalMass;
			mt += child.totalMass;
		}
	}

	if (mt > 0) {
		node.comX = mx / mt;
		node.comY = my / mt;
		node.comZ = mz / mt;
	}
	node.totalMass = mt;
}

export interface ForceAccumulator {
	fx: number;
	fy: number;
	fz: number;
}

/**
 * Build an octree from a list of bodies.
 * Returns the root node, ready for force queries.
 */
export function buildOctree(bodies: OctreeBody[]): OctreeNode | null {
	if (bodies.length === 0) return null;

	// Compute bounding box
	let minX = Infinity,
		minY = Infinity,
		minZ = Infinity;
	let maxX = -Infinity,
		maxY = -Infinity,
		maxZ = -Infinity;

	for (const b of bodies) {
		if (b.x < minX) minX = b.x;
		if (b.y < minY) minY = b.y;
		if (b.z < minZ) minZ = b.z;
		if (b.x > maxX) maxX = b.x;
		if (b.y > maxY) maxY = b.y;
		if (b.z > maxZ) maxZ = b.z;
	}

	const cx = (minX + maxX) * 0.5;
	const cy = (minY + maxY) * 0.5;
	const cz = (minZ + maxZ) * 0.5;
	const halfSize = Math.max(maxX - minX, maxY - minY, maxZ - minZ) * 0.5 + 1;

	const root = createNode(cx, cy, cz, halfSize);

	for (const b of bodies) {
		insertBody(root, b, 0);
	}

	computeCOM(root);
	return root;
}

/**
 * Compute the repulsive force on a single body from the octree.
 * Uses Barnes-Hut approximation: if a cell's width/distance ratio < theta,
 * treat the entire cell as a single point mass at its center of mass.
 *
 * @param theta - Accuracy parameter (0.5 = accurate, 1.0 = fast). Default 0.8.
 * @param chargeStrength - Negative for repulsion (Coulomb-like).
 * @param maxDist - Maximum interaction distance.
 */
export function computeForce(
	root: OctreeNode,
	body: OctreeBody,
	theta: number,
	chargeStrength: number,
	maxDist: number
): ForceAccumulator {
	const acc: ForceAccumulator = { fx: 0, fy: 0, fz: 0 };
	_walkForce(root, body, theta, chargeStrength, maxDist * maxDist, acc);
	return acc;
}

function _walkForce(
	node: OctreeNode,
	body: OctreeBody,
	theta: number,
	strength: number,
	maxDist2: number,
	acc: ForceAccumulator
): void {
	if (node.totalMass === 0) return;

	let dx = node.comX - body.x;
	let dy = node.comY - body.y;
	let dz = node.comZ - body.z;
	let dist2 = dx * dx + dy * dy + dz * dz;

	// Skip if beyond max distance
	if (dist2 > maxDist2) return;

	const cellSize = node.halfSize * 2;

	// Leaf node with a single body
	if (node.body !== null) {
		if (node.body.id === body.id) return; // Skip self

		if (dist2 < 0.01) {
			// Jitter overlapping points
			dx = (Math.random() - 0.5) * 0.1;
			dy = (Math.random() - 0.5) * 0.1;
			dz = (Math.random() - 0.5) * 0.1;
			dist2 = dx * dx + dy * dy + dz * dz;
		}

		const dist = Math.sqrt(dist2);
		// Softened inverse-square: F = strength * m1 * m2 / (dist² + softening)
		const force = (strength * body.mass * node.body.mass) / (dist2 + 0.1);
		acc.fx += (dx / dist) * force;
		acc.fy += (dy / dist) * force;
		acc.fz += (dz / dist) * force;
		return;
	}

	// Barnes-Hut criterion: if cell is far enough, approximate
	if (cellSize * cellSize < theta * theta * dist2) {
		if (dist2 < 0.01) return;
		const dist = Math.sqrt(dist2);
		const force = (strength * body.mass * node.totalMass) / (dist2 + 0.1);
		acc.fx += (dx / dist) * force;
		acc.fy += (dy / dist) * force;
		acc.fz += (dz / dist) * force;
		return;
	}

	// Otherwise recurse into children
	if (node.children) {
		for (const child of node.children) {
			if (child) {
				_walkForce(child, body, theta, strength, maxDist2, acc);
			}
		}
	}
}
