/**
 * 3D force-directed layout engine with:
 * - Barnes-Hut octree for O(n log n) repulsion
 * - Energy-based cooling (not linear alpha decay)
 * - Velocity Verlet integration
 * - Degree-based mass
 * - Localized reheat on graph changes
 */

import { buildOctree, computeForce, type OctreeBody } from './octree';

export interface LayoutNode {
	id: string;
	x: number;
	y: number;
	z: number;
	vx: number;
	vy: number;
	vz: number;
	// Current acceleration
	ax: number;
	ay: number;
	az: number;
	// Previous-tick acceleration (for full Verlet velocity update)
	axPrev: number;
	ayPrev: number;
	azPrev: number;
	fx: number | null; // pinned position (null = unpinned)
	fy: number | null;
	fz: number | null;
	radius: number;
	mass: number;
	degree: number;
}

export interface LayoutLink {
	source: string;
	target: string;
	weight: number; // edge weight — stronger edges pull tighter
}

export interface ForceLayoutOptions {
	linkDistance?: number;
	linkStrength?: number;
	chargeStrength?: number;
	chargeDistanceMax?: number;
	centerStrength?: number;
	collisionPadding?: number;
	damping?: number;
	/** Energy threshold below which we stop ticking. */
	energyMin?: number;
	/** Barnes-Hut theta (0.5 = accurate, 1.0 = fast). */
	theta?: number;
}

const DEFAULTS: Required<ForceLayoutOptions> = {
	linkDistance: 5,
	linkStrength: 0.3,
	chargeStrength: -15,
	chargeDistanceMax: 30,
	centerStrength: 0.012,
	collisionPadding: 0.4,
	damping: 0.86,
	energyMin: 0.002,
	theta: 0.8
};

export class ForceLayout {
	nodes: Map<string, LayoutNode> = new Map();
	links: LayoutLink[] = [];
	energy = Infinity;
	private opts: Required<ForceLayoutOptions>;
	private adjacency: Map<string, Set<string>> = new Map();

	constructor(opts: ForceLayoutOptions = {}) {
		this.opts = { ...DEFAULTS, ...opts };
	}

	/** Replace all nodes and links. Preserves positions for existing node IDs. */
	setGraph(
		nodeData: Array<{ id: string; radius: number }>,
		linkData: Array<{ source: string; target: string; weight?: number }>
	) {
		const oldNodes = this.nodes;
		this.nodes = new Map();

		const nodeIds = new Set(nodeData.map((n) => n.id));

		// Build adjacency first to compute degree
		const tempAdj = new Map<string, Set<string>>();
		const validLinks = linkData.filter((l) => nodeIds.has(l.source) && nodeIds.has(l.target));
		for (const link of validLinks) {
			if (!tempAdj.has(link.source)) tempAdj.set(link.source, new Set());
			if (!tempAdj.has(link.target)) tempAdj.set(link.target, new Set());
			tempAdj.get(link.source)!.add(link.target);
			tempAdj.get(link.target)!.add(link.source);
		}

		for (let i = 0; i < nodeData.length; i++) {
			const d = nodeData[i];
			const degree = tempAdj.get(d.id)?.size ?? 0;
			const existing = oldNodes.get(d.id);
			if (existing) {
				existing.radius = d.radius;
				existing.mass = 1 + degree * 0.5;
				existing.degree = degree;
				this.nodes.set(d.id, existing);
			} else {
				// Golden-angle spiral placement in 3D — wide spread to reduce initial forces
				const angle = i * 2.399963; // golden angle in radians
				const r = 3 + i * 0.6;
				const layer = ((i % 3) - 1) * 2.5;
				this.nodes.set(d.id, {
					id: d.id,
					x: r * Math.cos(angle),
					y: layer + (Math.random() - 0.5) * 0.5,
					z: r * Math.sin(angle),
					vx: 0,
					vy: 0,
					vz: 0,
					ax: 0,
					ay: 0,
					az: 0,
					axPrev: 0,
					ayPrev: 0,
					azPrev: 0,
					fx: null,
					fy: null,
					fz: null,
					radius: d.radius,
					mass: 1 + degree * 0.5,
					degree
				});
			}
		}

		this.links = validLinks.map((l) => ({
			source: l.source,
			target: l.target,
			weight: l.weight ?? 1
		}));

		this.adjacency = tempAdj;
		this.energy = Infinity;

		// Warm start: run simulation silently to skip the chaotic initial phase.
		// Nodes converge to a rough layout before the first render frame.
		for (let i = 0; i < 60; i++) {
			if (!this.tick()) break;
		}
	}

	/** Advance one tick using velocity Verlet. Returns true if still settling. */
	tick(): boolean {
		if (this.energy < this.opts.energyMin) return false;

		const nodes = Array.from(this.nodes.values());
		const n = nodes.length;
		if (n === 0) {
			this.energy = 0;
			return false;
		}

		// --- Half-step position update (Verlet part 1) ---
		const dt = 1;
		for (const node of nodes) {
			if (node.fx !== null) continue;
			node.x += node.vx * dt + 0.5 * node.ax * dt * dt;
			node.y += node.vy * dt + 0.5 * node.ay * dt * dt;
			node.z += node.vz * dt + 0.5 * node.az * dt * dt;
		}

		// --- Compute forces ---
		// Store previous accelerations for full Verlet velocity update
		for (const node of nodes) {
			node.axPrev = node.ax;
			node.ayPrev = node.ay;
			node.azPrev = node.az;
			node.ax = 0;
			node.ay = 0;
			node.az = 0;
		}

		// Charge (repulsion) via Barnes-Hut octree
		this._applyChargeForces(nodes);

		// Link (spring) forces
		this._applyLinkForces();

		// Center gravity
		this._applyCenterGravity(nodes);

		// Collision resolution
		this._resolveCollisions(nodes, n);

		// --- Half-step velocity update (Verlet part 2) + damping ---
		let totalEnergy = 0;
		for (const node of nodes) {
			// NaN recovery
			if (!isFinite(node.ax)) node.ax = 0;
			if (!isFinite(node.ay)) node.ay = 0;
			if (!isFinite(node.az)) node.az = 0;
			if (!isFinite(node.x)) node.x = (Math.random() - 0.5) * 2;
			if (!isFinite(node.y)) node.y = (Math.random() - 0.5) * 2;
			if (!isFinite(node.z)) node.z = (Math.random() - 0.5) * 2;

			if (node.fx !== null) {
				node.x = node.fx;
				node.vx = 0;
			}
			if (node.fy !== null) {
				node.y = node.fy;
				node.vy = 0;
			}
			if (node.fz !== null) {
				node.z = node.fz;
				node.vz = 0;
			}

			if (node.fx === null && node.fy === null && node.fz === null) {
				// Full velocity Verlet: v += 0.5 * (a_prev + a_new) * dt
				node.vx += 0.5 * (node.axPrev + node.ax) * dt;
				node.vy += 0.5 * (node.ayPrev + node.ay) * dt;
				node.vz += 0.5 * (node.azPrev + node.az) * dt;

				// Smooth velocity limiting — tanh-style soft clamp.
				// Approaches maxV asymptotically instead of hard clamping.
				const maxV = 4;
				const speed = Math.sqrt(
					node.vx * node.vx + node.vy * node.vy + node.vz * node.vz
				);
				if (speed > 0.001) {
					const clamped = maxV * Math.tanh(speed / maxV);
					const scale = clamped / speed;
					node.vx *= scale;
					node.vy *= scale;
					node.vz *= scale;
				}

				// Smooth damping — constant rate gives natural deceleration
				node.vx *= this.opts.damping;
				node.vy *= this.opts.damping;
				node.vz *= this.opts.damping;
			}

			// Kinetic energy (per node, mass-weighted)
			totalEnergy +=
				0.5 * node.mass * (node.vx * node.vx + node.vy * node.vy + node.vz * node.vz);
		}

		this.energy = totalEnergy / Math.max(n, 1);
		return true;
	}

	private _applyChargeForces(nodes: LayoutNode[]) {
		// Build octree bodies
		const bodies: OctreeBody[] = nodes.map((n) => ({
			x: n.x,
			y: n.y,
			z: n.z,
			mass: n.mass,
			id: n.id
		}));

		const root = buildOctree(bodies);
		if (!root) return;

		for (const node of nodes) {
			if (node.fx !== null && node.fy !== null && node.fz !== null) continue;

			const body: OctreeBody = {
				x: node.x,
				y: node.y,
				z: node.z,
				mass: node.mass,
				id: node.id
			};

			const force = computeForce(
				root,
				body,
				this.opts.theta,
				this.opts.chargeStrength,
				this.opts.chargeDistanceMax
			);

			node.ax += force.fx / node.mass;
			node.ay += force.fy / node.mass;
			node.az += force.fz / node.mass;
		}
	}

	private _applyLinkForces() {
		for (const link of this.links) {
			const a = this.nodes.get(link.source);
			const b = this.nodes.get(link.target);
			if (!a || !b) continue;

			let dx = b.x - a.x;
			let dy = b.y - a.y;
			let dz = b.z - a.z;
			let dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
			if (dist < 0.01) dist = 0.01;

			// Rest length inversely proportional to edge weight
			const restLength = this.opts.linkDistance / Math.max(link.weight, 0.1);
			const displacement = dist - restLength;

			// Spring force with critical damping term
			const springForce = displacement * this.opts.linkStrength;

			// Relative velocity along the spring axis (for damping)
			const nx = dx / dist;
			const ny = dy / dist;
			const nz = dz / dist;
			const relVel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny + (b.vz - a.vz) * nz;
			const dampingForce = relVel * 0.25; // spring-local damping — higher = more elastic feel

			const totalForce = springForce + dampingForce;
			const forceX = nx * totalForce;
			const forceY = ny * totalForce;
			const forceZ = nz * totalForce;

			a.ax += forceX / a.mass;
			a.ay += forceY / a.mass;
			a.az += forceZ / a.mass;
			b.ax -= forceX / b.mass;
			b.ay -= forceY / b.mass;
			b.az -= forceZ / b.mass;
		}
	}

	private _applyCenterGravity(nodes: LayoutNode[]) {
		for (const node of nodes) {
			if (node.fx !== null && node.fy !== null && node.fz !== null) continue;
			node.ax -= node.x * this.opts.centerStrength;
			node.ay -= node.y * this.opts.centerStrength;
			node.az -= node.z * this.opts.centerStrength;
		}
	}

	private _resolveCollisions(nodes: LayoutNode[], n: number) {
		// O(n²) but only for overlapping pairs — fine for <200 nodes
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
					const overlap = (minDist - dist) * 0.3;
					const nx = dx / dist;
					const ny = dy / dist;
					const nz = dz / dist;
					// Position correction
					a.x -= nx * overlap;
					a.y -= ny * overlap;
					a.z -= nz * overlap;
					b.x += nx * overlap;
					b.y += ny * overlap;
					b.z += nz * overlap;
					// Gentle velocity correction — absorb rather than bounce
					const relV = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny + (b.vz - a.vz) * nz;
					if (relV < 0) {
						const impulse = relV * 0.15;
						a.vx += nx * impulse;
						a.vy += ny * impulse;
						a.vz += nz * impulse;
						b.vx -= nx * impulse;
						b.vy -= ny * impulse;
						b.vz -= nz * impulse;
					}
				}
			}
		}
	}

	/** Reheat simulation (e.g. after dragging or graph change).
	 *  Only raises the energy threshold so the simulation keeps ticking.
	 *  Does NOT inject random velocity — forces handle repositioning. */
	reheat(energy = 2) {
		this.energy = Math.max(this.energy, energy);
	}

	/**
	 * Localized reheat — only disturbs nodes within `hops` of `centerId`.
	 * Used when a hop adds/changes nodes to avoid exploding the whole graph.
	 */
	reheatLocal(centerId: string, hops = 2, energy = 2) {
		this.energy = Math.max(this.energy, energy);
		// No velocity kicks — forces handle repositioning naturally
	}

	private _bfsNeighbors(startId: string, maxHops: number): Set<string> {
		const visited = new Set<string>();
		const queue: Array<{ id: string; depth: number }> = [{ id: startId, depth: 0 }];
		visited.add(startId);
		while (queue.length > 0) {
			const { id, depth } = queue.shift()!;
			if (depth >= maxHops) continue;
			const neighbors = this.adjacency.get(id);
			if (neighbors) {
				for (const nid of neighbors) {
					if (!visited.has(nid)) {
						visited.add(nid);
						queue.push({ id: nid, depth: depth + 1 });
					}
				}
			}
		}
		return visited;
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

	/** Unpin and impart drag momentum for natural release. */
	releaseWithVelocity(id: string, vx: number, vy: number, vz: number) {
		const node = this.nodes.get(id);
		if (node) {
			node.fx = null;
			node.fy = null;
			node.fz = null;
			// Clamp momentum to avoid wild flings
			const maxV = 3;
			const speed = Math.sqrt(vx * vx + vy * vy + vz * vz);
			const scale = speed > maxV ? maxV / speed : 1;
			node.vx = vx * scale;
			node.vy = vy * scale;
			node.vz = vz * scale;
		}
	}
}
