/**
 * Lightweight 3D force-directed layout engine.
 * No dependencies — replaces d3-force for our use case.
 */

export interface LayoutNode {
	id: string;
	x: number;
	y: number;
	z: number;
	vx: number;
	vy: number;
	vz: number;
	fx: number | null; // pinned position (null = unpinned)
	fy: number | null;
	fz: number | null;
	radius: number;
	mass: number;
}

export interface LayoutLink {
	source: string;
	target: string;
}

export interface ForceLayoutOptions {
	linkDistance?: number;
	linkStrength?: number;
	chargeStrength?: number;
	chargeDistanceMax?: number;
	centerStrength?: number;
	collisionPadding?: number;
	damping?: number;
	alphaDecay?: number;
	alphaMin?: number;
}

const DEFAULTS: Required<ForceLayoutOptions> = {
	linkDistance: 4,
	linkStrength: 0.6,
	chargeStrength: -8,
	chargeDistanceMax: 20,
	centerStrength: 0.02,
	collisionPadding: 0.3,
	damping: 0.85,
	alphaDecay: 0.005,
	alphaMin: 0.001
};

export class ForceLayout {
	nodes: Map<string, LayoutNode> = new Map();
	links: LayoutLink[] = [];
	alpha = 1;
	private opts: Required<ForceLayoutOptions>;
	private adjacency: Map<string, Set<string>> = new Map();

	constructor(opts: ForceLayoutOptions = {}) {
		this.opts = { ...DEFAULTS, ...opts };
	}

	/** Replace all nodes and links. Preserves positions for existing node IDs. */
	setGraph(
		nodeData: Array<{ id: string; radius: number }>,
		linkData: Array<{ source: string; target: string }>
	) {
		const oldNodes = this.nodes;
		this.nodes = new Map();

		const nodeIds = new Set(nodeData.map((n) => n.id));

		for (let i = 0; i < nodeData.length; i++) {
			const d = nodeData[i];
			const existing = oldNodes.get(d.id);
			if (existing) {
				existing.radius = d.radius;
				this.nodes.set(d.id, existing);
			} else {
				// Spiral placement in 3D
				const angle = i * 0.618 * Math.PI * 2; // golden angle
				const r = 2 + i * 0.3;
				const layer = (i % 3 - 1) * 1.5; // spread across y layers
				this.nodes.set(d.id, {
					id: d.id,
					x: r * Math.cos(angle),
					y: layer + (Math.random() - 0.5) * 0.5,
					z: r * Math.sin(angle),
					vx: 0,
					vy: 0,
					vz: 0,
					fx: null,
					fy: null,
					fz: null,
					radius: d.radius,
					mass: 1
				});
			}
		}

		// Only keep links where both endpoints exist
		this.links = linkData.filter((l) => nodeIds.has(l.source) && nodeIds.has(l.target));

		// Build adjacency
		this.adjacency.clear();
		for (const link of this.links) {
			if (!this.adjacency.has(link.source)) this.adjacency.set(link.source, new Set());
			if (!this.adjacency.has(link.target)) this.adjacency.set(link.target, new Set());
			this.adjacency.get(link.source)!.add(link.target);
			this.adjacency.get(link.target)!.add(link.source);
		}

		// Reheat
		this.alpha = 1;
	}

	/** Advance one tick. Returns true if still settling. */
	tick(): boolean {
		if (this.alpha < this.opts.alphaMin) return false;

		const nodes = Array.from(this.nodes.values());
		const n = nodes.length;
		if (n === 0) return false;

		// --- Charge (repulsion) ---
		for (let i = 0; i < n; i++) {
			for (let j = i + 1; j < n; j++) {
				const a = nodes[i];
				const b = nodes[j];
				let dx = b.x - a.x;
				let dy = b.y - a.y;
				let dz = b.z - a.z;
				let dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
				if (dist > this.opts.chargeDistanceMax) continue;
				if (dist < 0.1) {
					dx = (Math.random() - 0.5) * 0.1;
					dy = (Math.random() - 0.5) * 0.1;
					dz = (Math.random() - 0.5) * 0.1;
					dist = 0.1;
				}
				const force = (this.opts.chargeStrength * this.alpha) / (dist * dist);
				const fx = (dx / dist) * force;
				const fy = (dy / dist) * force;
				const fz = (dz / dist) * force;
				a.vx -= fx;
				a.vy -= fy;
				a.vz -= fz;
				b.vx += fx;
				b.vy += fy;
				b.vz += fz;
			}
		}

		// --- Link (spring) ---
		for (const link of this.links) {
			const a = this.nodes.get(link.source);
			const b = this.nodes.get(link.target);
			if (!a || !b) continue;
			let dx = b.x - a.x;
			let dy = b.y - a.y;
			let dz = b.z - a.z;
			let dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
			if (dist < 0.01) dist = 0.01;
			const displacement = dist - this.opts.linkDistance;
			const force = displacement * this.opts.linkStrength * this.alpha;
			const fx = (dx / dist) * force;
			const fy = (dy / dist) * force;
			const fz = (dz / dist) * force;
			a.vx += fx;
			a.vy += fy;
			a.vz += fz;
			b.vx -= fx;
			b.vy -= fy;
			b.vz -= fz;
		}

		// --- Center gravity ---
		for (const node of nodes) {
			node.vx -= node.x * this.opts.centerStrength * this.alpha;
			node.vy -= node.y * this.opts.centerStrength * this.alpha;
			node.vz -= node.z * this.opts.centerStrength * this.alpha;
		}

		// --- Collision ---
		for (let i = 0; i < n; i++) {
			for (let j = i + 1; j < n; j++) {
				const a = nodes[i];
				const b = nodes[j];
				const dx = b.x - a.x;
				const dy = b.y - a.y;
				const dz = b.z - a.z;
				const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
				const minDist = a.radius + b.radius + this.opts.collisionPadding;
				if (dist < minDist && dist > 0.001) {
					const overlap = (minDist - dist) * 0.5;
					const nx = dx / dist;
					const ny = dy / dist;
					const nz = dz / dist;
					a.x -= nx * overlap;
					a.y -= ny * overlap;
					a.z -= nz * overlap;
					b.x += nx * overlap;
					b.y += ny * overlap;
					b.z += nz * overlap;
				}
			}
		}

		// --- Integrate ---
		for (const node of nodes) {
			// Clamp velocities to prevent explosion
			const maxV = 10;
			node.vx = Math.max(-maxV, Math.min(maxV, node.vx));
			node.vy = Math.max(-maxV, Math.min(maxV, node.vy));
			node.vz = Math.max(-maxV, Math.min(maxV, node.vz));

			// NaN recovery — reset to origin with jitter
			if (!isFinite(node.vx)) node.vx = 0;
			if (!isFinite(node.vy)) node.vy = 0;
			if (!isFinite(node.vz)) node.vz = 0;
			if (!isFinite(node.x)) node.x = (Math.random() - 0.5) * 2;
			if (!isFinite(node.y)) node.y = (Math.random() - 0.5) * 2;
			if (!isFinite(node.z)) node.z = (Math.random() - 0.5) * 2;

			if (node.fx !== null) {
				node.x = node.fx;
				node.vx = 0;
			} else {
				node.vx *= this.opts.damping;
				node.x += node.vx;
			}
			if (node.fy !== null) {
				node.y = node.fy;
				node.vy = 0;
			} else {
				node.vy *= this.opts.damping;
				node.y += node.vy;
			}
			if (node.fz !== null) {
				node.z = node.fz;
				node.vz = 0;
			} else {
				node.vz *= this.opts.damping;
				node.z += node.vz;
			}
		}

		this.alpha -= this.opts.alphaDecay;
		return true;
	}

	/** Reheat simulation (e.g. after dragging). */
	reheat(alpha = 0.5) {
		this.alpha = Math.max(this.alpha, alpha);
	}

	/** Pin a node to a position. */
	pin(id: string, x: number, y: number, z: number) {
		const node = this.nodes.get(id);
		if (node) {
			node.fx = x;
			node.fy = y;
			node.fz = z;
		}
	}

	/** Unpin a node. */
	unpin(id: string) {
		const node = this.nodes.get(id);
		if (node) {
			node.fx = null;
			node.fy = null;
			node.fz = null;
		}
	}
}
