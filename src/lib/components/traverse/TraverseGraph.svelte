<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';

	interface Props {
		nodes: Array<{ node_id: string; has_corpus: boolean; neighbours: string[] }>;
		edges: Array<{ source_id: string; dest_id: string; weight: number; traversal_count: number }>;
		playerPath: string[];
		currentNodeId: string | null;
	}

	let { nodes = [], edges = [], playerPath = [], currentNodeId = null }: Props = $props();

	interface GraphNode extends d3.SimulationNodeDatum {
		id: string;
		has_corpus: boolean;
		radius: number;
	}

	interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
		weight: number;
		traversal_count: number;
		isPath: boolean;
	}

	let container: HTMLDivElement;
	let mounted = $state(false);

	function buildGraph() {
		if (!container || !mounted) return;

		d3.select(container).selectAll('svg').remove();

		const rect = container.getBoundingClientRect();
		const width = rect.width || 900;
		const height = Math.max(rect.height, 400);

		const nodeIds = new Set(nodes.map((n) => n.node_id));
		const pathSet = new Set(playerPath);
		const pathEdgeSet = new Set<string>();
		for (let i = 0; i < playerPath.length - 1; i++) {
			pathEdgeSet.add(`${playerPath[i]}__${playerPath[i + 1]}`);
			pathEdgeSet.add(`${playerPath[i + 1]}__${playerPath[i]}`);
		}

		const simNodes: GraphNode[] = nodes.map((n, i) => {
			const angle = (i / nodes.length) * 2 * Math.PI;
			const r = Math.min(width, height) * 0.32;
			return {
				id: n.node_id,
				has_corpus: n.has_corpus,
				radius: n.node_id === currentNodeId ? 12 : pathSet.has(n.node_id) ? 9 : 6,
				x: width / 2 + r * Math.cos(angle),
				y: height / 2 + r * Math.sin(angle)
			};
		});

		const simLinks: GraphLink[] = edges
			.filter((e) => nodeIds.has(e.source_id) && nodeIds.has(e.dest_id))
			.map((e) => ({
				source: e.source_id,
				target: e.dest_id,
				weight: e.weight,
				traversal_count: e.traversal_count,
				isPath: pathEdgeSet.has(`${e.source_id}__${e.dest_id}`)
			}));

		const svg = d3
			.select(container)
			.append('svg')
			.attr('width', '100%')
			.attr('height', '100%')
			.attr('viewBox', [0, 0, width, height]);

		// Radial gradient background
		const defs = svg.append('defs');
		const grad = defs
			.append('radialGradient')
			.attr('id', 'tg-bg')
			.attr('cx', '50%')
			.attr('cy', '50%')
			.attr('r', '50%');
		grad.append('stop').attr('offset', '0%').attr('stop-color', '#0f172a');
		grad.append('stop').attr('offset', '100%').attr('stop-color', '#020617');

		svg.append('rect').attr('width', width).attr('height', height).attr('fill', 'url(#tg-bg)');

		// Glow filter for path nodes and edges
		const filter = defs.append('filter').attr('id', 'tg-glow').attr('x', '-50%').attr('y', '-50%').attr('width', '200%').attr('height', '200%');
		filter.append('feGaussianBlur').attr('in', 'SourceGraphic').attr('stdDeviation', '3').attr('result', 'blur');
		const merge = filter.append('feMerge');
		merge.append('feMergeNode').attr('in', 'blur');
		merge.append('feMergeNode').attr('in', 'SourceGraphic');

		const g = svg.append('g');

		svg.call(
			d3
				.zoom<SVGSVGElement, unknown>()
				.scaleExtent([0.2, 5])
				.on('zoom', (event) => g.attr('transform', event.transform))
		);

		const simulation = d3
			.forceSimulation(simNodes)
			.force(
				'link',
				d3
					.forceLink<GraphNode, GraphLink>(simLinks)
					.id((d) => d.id)
					.distance(80)
					.strength(0.6)
			)
			.force('charge', d3.forceManyBody().strength(-120).distanceMax(400))
			.force('center', d3.forceCenter(width / 2, height / 2).strength(0.08))
			.force('collision', d3.forceCollide().radius((d) => (d as GraphNode).radius + 8));

		// Edges
		const link = g
			.append('g')
			.selectAll('line')
			.data(simLinks)
			.join('line')
			.attr('stroke', (d) => (d.isPath ? '#6ee7b7' : '#1e293b'))
			.attr('stroke-opacity', (d) => (d.isPath ? 0.9 : 0.5))
			.attr('stroke-width', (d) => {
				if (d.isPath) return 3;
				return Math.max(1, (d.weight ?? 0.5) * 3);
			})
			.attr('filter', (d) => (d.isPath ? 'url(#tg-glow)' : null));

		// Node circles
		const node = g
			.append('g')
			.selectAll<SVGCircleElement, GraphNode>('circle')
			.data(simNodes)
			.join('circle')
			.attr('r', (d) => d.radius)
			.attr('fill', (d) => {
				if (d.id === currentNodeId) return '#6ee7b7';
				if (pathSet.has(d.id)) return '#34d399';
				return d.has_corpus ? '#93c5fd' : '#475569';
			})
			.attr('fill-opacity', (d) => {
				if (d.id === currentNodeId || pathSet.has(d.id)) return 1;
				return 0.5;
			})
			.attr('stroke', (d) => {
				if (d.id === currentNodeId) return '#ffffff';
				if (pathSet.has(d.id)) return '#6ee7b7';
				return '#1e293b';
			})
			.attr('stroke-width', (d) => (d.id === currentNodeId ? 2.5 : 1.5))
			.attr('filter', (d) =>
				d.id === currentNodeId || pathSet.has(d.id) ? 'url(#tg-glow)' : null
			)
			.attr('cursor', 'default')
			.call(
				d3
					.drag<SVGCircleElement, GraphNode>()
					.on('start', (event, d) => {
						if (!event.active) simulation.alphaTarget(0.3).restart();
						d.fx = d.x;
						d.fy = d.y;
					})
					.on('drag', (event, d) => {
						d.fx = event.x;
						d.fy = event.y;
					})
					.on('end', (event, d) => {
						if (!event.active) simulation.alphaTarget(0);
						d.fx = null;
						d.fy = null;
					})
			);

		// Node labels — all nodes shown (small graph)
		const labels = g
			.append('g')
			.selectAll<SVGTextElement, GraphNode>('text')
			.data(simNodes)
			.join('text')
			.text((d) => d.id)
			.attr('font-size', (d) => (d.id === currentNodeId ? '11px' : '10px'))
			.attr('fill', (d) => {
				if (d.id === currentNodeId) return '#6ee7b7';
				if (pathSet.has(d.id)) return '#a7f3d0';
				return '#64748b';
			})
			.attr('font-weight', (d) => (d.id === currentNodeId ? '700' : '400'))
			.attr('text-anchor', 'middle')
			.attr('dy', (d) => d.radius + 13)
			.attr('pointer-events', 'none');

		simulation.on('tick', () => {
			link
				.attr('x1', (d) => (d.source as GraphNode).x!)
				.attr('y1', (d) => (d.source as GraphNode).y!)
				.attr('x2', (d) => (d.target as GraphNode).x!)
				.attr('y2', (d) => (d.target as GraphNode).y!);
			node.attr('cx', (d) => d.x!).attr('cy', (d) => d.y!);
			labels.attr('x', (d) => d.x!).attr('y', (d) => d.y!);
		});
	}

	onMount(() => {
		mounted = true;
		buildGraph();
		const ro = new ResizeObserver(() => buildGraph());
		ro.observe(container);
		return () => ro.disconnect();
	});

	$effect(() => {
		if (mounted) {
			// Reactive dependencies
			nodes;
			edges;
			playerPath;
			currentNodeId;
			buildGraph();
		}
	});
</script>

<div class="graph-container" bind:this={container}></div>

<style>
	.graph-container {
		position: relative;
		width: 100%;
		height: 100%;
		min-height: 300px;
		border-radius: 12px;
		overflow: hidden;
	}
</style>
