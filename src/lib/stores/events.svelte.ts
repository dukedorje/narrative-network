/**
 * Network events store — SSE-backed reactive feed of subnet activity.
 *
 * Connects to /api/events/stream (SvelteKit proxy → gateway /events/stream)
 * and maintains a capped rolling buffer of recent events.
 *
 * Usage (Svelte 5 runes):
 *   import { eventsStore } from '$lib/stores/events.svelte';
 *
 *   eventsStore.connect();
 *   // In template: {#each eventsStore.events as ev} ... {/each}
 *   // On teardown: eventsStore.disconnect();
 */

import { NetworkEvent, EventsRecentResponse } from '$lib/api/schemas';
import type { NetworkEvent as NetworkEventT } from '$lib/api/schemas';

// ── Constants ────────────────────────────────────────────────────────

const MAX_EVENTS = 200;
const RECONNECT_DELAY_MS = 3000;

// ── Types ────────────────────────────────────────────────────────────

export type EventsStatus = 'idle' | 'connecting' | 'connected' | 'error' | 'closed';

// ── Store ────────────────────────────────────────────────────────────

function createEventsStore() {
	let events = $state<NetworkEventT[]>([]);
	let status = $state<EventsStatus>('idle');
	let error = $state<string | null>(null);

	let source: EventSource | null = null;
	let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
	let filter: string | null = null;
	let stopped = false;

	function buildUrl(): string {
		const base = '/api/events/stream';
		return filter ? `${base}?filter=${encodeURIComponent(filter)}` : base;
	}

	function clearReconnect() {
		if (reconnectTimer !== null) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
	}

	function open() {
		if (source) {
			source.close();
			source = null;
		}

		status = 'connecting';
		const es = new EventSource(buildUrl());
		source = es;

		es.addEventListener('open', () => {
			if (es !== source) return;
			status = 'connected';
			error = null;
		});

		es.addEventListener('message', (e: MessageEvent) => {
			if (es !== source) return;
			try {
				const raw = JSON.parse(e.data);
				const event = NetworkEvent.parse(raw);
				events = [event, ...events].slice(0, MAX_EVENTS);
			} catch {
				// Malformed event — silently drop
			}
		});

		es.addEventListener('error', () => {
			if (es !== source) return;
			status = 'error';
			error = 'Connection lost';
			es.close();
			source = null;

			if (!stopped) {
				reconnectTimer = setTimeout(() => {
					if (!stopped) open();
				}, RECONNECT_DELAY_MS);
			}
		});
	}

	return {
		get events() {
			return events;
		},
		get status() {
			return status;
		},
		get error() {
			return error;
		},

		/**
		 * Start streaming events. Optionally filter by event_type prefix.
		 * Safe to call multiple times — reconnects cleanly.
		 */
		connect(eventFilter?: string) {
			stopped = false;
			filter = eventFilter ?? null;
			clearReconnect();
			open();
		},

		/** Stop streaming and clear the reconnect timer. */
		disconnect() {
			stopped = true;
			clearReconnect();
			if (source) {
				source.close();
				source = null;
			}
			status = 'closed';
		},

		/** Fetch recent events from REST endpoint and prepend to buffer. */
		async loadRecent(opts?: { limit?: number; component?: string }) {
			const params = new URLSearchParams({ limit: String(opts?.limit ?? 50) });
			if (opts?.component) params.set('component', opts.component);
			try {
				const res = await fetch(`/api/events/recent?${params}`);
				if (!res.ok) return;
				const data = await res.json();
				const validated = EventsRecentResponse.parse(data);
				const parsed = validated.events;
				// Merge without duplicates (by correlation_id), preserve order
				const existing = new Set(events.map((e) => e.correlation_id));
				const fresh = parsed.filter((e) => !existing.has(e.correlation_id));
				events = [...events, ...fresh].slice(0, MAX_EVENTS);
			} catch {
				// Non-critical — silently ignore
			}
		},

		/** Clear the in-memory event buffer. */
		clear() {
			events = [];
		}
	};
}

export const eventsStore = createEventsStore();
