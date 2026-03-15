<script lang="ts">
	import { onMount } from 'svelte';
	import * as d3 from 'd3';

	interface GraphNode extends d3.SimulationNodeDatum {
		id: string;
		name: string;
		type: string;
		summary?: string;
		labels?: string[];
		radius: number;
	}

	interface GraphLink extends d3.SimulationLinkDatum<GraphNode> {
		id: string;
		edgeType: string;
		fact?: string;
	}

	let {
		entities = [],
		edges = [],
		onNodeClick
	}: {
		entities: Array<{
			uuid: string;
			name: string;
			node_type: string;
			summary?: string;
			labels?: string[];
		}>;
		edges: Array<{
			uuid: string;
			edge_type: string;
			source_node_uuid: string;
			target_node_uuid: string;
			fact?: string | null;
		}>;
		onNodeClick?: (uuid: string, name: string) => void;
	} = $props();

	let container: HTMLDivElement;
	let tooltip: HTMLDivElement;
	let mounted = $state(false);

	function buildGraph() {
		if (!container || !mounted) return;

		// Clear previous
		d3.select(container).selectAll('svg').remove();

		const rect = container.getBoundingClientRect();
		const width = rect.width || 900;
		const height = Math.max(rect.height, 500);

		const entityUuids = new Set(entities.map((e) => e.uuid));

		const nodes: GraphNode[] = entities.map((e, i) => {
			// Spiral initial placement to avoid overlap
			const angle = i * 0.5;
			const r = 20 + i * 3;
			return {
				id: e.uuid,
				name: e.name,
				type: e.node_type,
				summary: e.summary,
				labels: e.labels,
				radius: 6 + Math.min(e.name.length * 0.3, 8),
				x: width / 2 + r * Math.cos(angle),
				y: height / 2 + r * Math.sin(angle)
			};
		});

		// Only include edges where both endpoints exist
		const links: GraphLink[] = edges
			.filter((e) => entityUuids.has(e.source_node_uuid) && entityUuids.has(e.target_node_uuid))
			.map((e) => ({
				id: e.uuid,
				source: e.source_node_uuid,
				target: e.target_node_uuid,
				edgeType: e.edge_type,
				fact: e.fact ?? undefined
			}));

		if (nodes.length === 0) return;

		const svg = d3
			.select(container)
			.append('svg')
			.attr('width', '100%')
			.attr('height', '100%')
			.attr('viewBox', [0, 0, width, height]);

		const g = svg.append('g');

		// Zoom + pan
		svg.call(
			d3
				.zoom<SVGSVGElement, unknown>()
				.scaleExtent([0.15, 5])
				.on('zoom', (event) => g.attr('transform', event.transform))
		);

		// Color by label/type
		const labelColors: Record<string, string> = {
			Entity: '#6ee7b7',
			TaxonomyLabel: '#93c5fd',
			Episodic: '#fbbf24',
			episode: '#f97316'
		};

		function nodeColor(d: GraphNode): string {
			if (d.labels?.length) {
				for (const label of d.labels) {
					if (labelColors[label]) return labelColors[label];
				}
			}
			return labelColors[d.type] ?? '#a78bfa';
		}

		const simulation = d3
			.forceSimulation(nodes)
			.force(
				'link',
				d3
					.forceLink<GraphNode, GraphLink>(links)
					.id((d) => d.id)
					.distance(60)
					.strength(0.8)
			)
			.force('charge', d3.forceManyBody().strength(-40).distanceMax(300))
			.force('center', d3.forceCenter(width / 2, height / 2).strength(0.1))
			.force('collision', d3.forceCollide().radius((d) => (d as GraphNode).radius + 3))
			.force('x', d3.forceX(width / 2).strength(0.08))
			.force('y', d3.forceY(height / 2).strength(0.08));

		// Edges
		const link = g
			.append('g')
			.selectAll('line')
			.data(links)
			.join('line')
			.attr('stroke', '#475569')
			.attr('stroke-opacity', 0.6)
			.attr('stroke-width', 1.5);

		// Nodes
		const node = g
			.append('g')
			.selectAll<SVGCircleElement, GraphNode>('circle')
			.data(nodes)
			.join('circle')
			.attr('r', (d) => d.radius)
			.attr('fill', nodeColor)
			.attr('fill-opacity', 0.85)
			.attr('stroke', '#1e293b')
			.attr('stroke-width', 1.5)
			.attr('cursor', 'pointer')
			.on('mouseover', function (_event, d) {
				d3.select(this).attr('fill-opacity', 1).attr('stroke', '#6ee7b7');
				if (tooltip) {
					tooltip.style.opacity = '1';
					tooltip.innerHTML = `
						<strong>${d.name}</strong>
						${d.summary ? `<p>${d.summary.slice(0, 200)}${d.summary.length > 200 ? '...' : ''}</p>` : ''}
						${d.labels?.length ? `<span class="labels">${d.labels.join(', ')}</span>` : ''}
					`;
				}
			})
			.on('mousemove', (event) => {
				if (tooltip) {
					const [x, y] = d3.pointer(event, container);
					tooltip.style.left = x + 15 + 'px';
					tooltip.style.top = y - 10 + 'px';
				}
			})
			.on('mouseout', function () {
				d3.select(this).attr('fill-opacity', 0.85).attr('stroke', '#1e293b');
				if (tooltip) tooltip.style.opacity = '0';
			})
			.on('click', (_event, d) => {
				onNodeClick?.(d.id, d.name);
			})
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

		// Labels (only for nodes with short-ish names)
		const nodeLabels = g
			.append('g')
			.selectAll<SVGTextElement, GraphNode>('text')
			.data(nodes.filter((n) => n.name.length <= 30))
			.join('text')
			.text((d) => (d.name.length > 20 ? d.name.slice(0, 18) + '...' : d.name))
			.attr('font-size', '10px')
			.attr('fill', '#94a3b8')
			.attr('text-anchor', 'middle')
			.attr('dy', (d) => d.radius + 12)
			.attr('pointer-events', 'none');

		simulation.on('tick', () => {
			link
				.attr('x1', (d) => (d.source as GraphNode).x!)
				.attr('y1', (d) => (d.source as GraphNode).y!)
				.attr('x2', (d) => (d.target as GraphNode).x!)
				.attr('y2', (d) => (d.target as GraphNode).y!);
			node.attr('cx', (d) => d.x!).attr('cy', (d) => d.y!);
			nodeLabels.attr('x', (d) => d.x!).attr('y', (d) => d.y!);
		});
	}

	onMount(() => {
		mounted = true;
		buildGraph();

		const ro = new ResizeObserver(() => {
			buildGraph();
		});
		ro.observe(container);
		return () => ro.disconnect();
	});

	$effect(() => {
		// Re-render when data changes (after mount)
		if (mounted) {
			entities;
			edges;
			buildGraph();
		}
	});
</script>

<div class="graph-container" bind:this={container}>
	<div class="tooltip" bind:this={tooltip}></div>
</div>

<style>
	.graph-container {
		position: relative;
		width: 100%;
		height: 100%;
		min-height: 500px;
		background: radial-gradient(ellipse at center, #0f172a 0%, #020617 100%);
		border-radius: 12px;
		overflow: hidden;
	}

	.tooltip {
		position: absolute;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		padding: 10px 14px;
		font-size: 13px;
		color: #e2e8f0;
		pointer-events: none;
		opacity: 0;
		transition: opacity 0.15s;
		max-width: 320px;
		z-index: 10;
	}

	.tooltip :global(p) {
		margin: 6px 0 0;
		font-size: 12px;
		color: #94a3b8;
		line-height: 1.4;
	}

	.tooltip :global(.labels) {
		display: block;
		margin-top: 4px;
		font-size: 11px;
		color: #6ee7b7;
	}
</style>
