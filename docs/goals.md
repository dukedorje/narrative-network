
# Goals

## Completed (2026-03-15)
- [x] Python subnet structure adopted from BNN-thom reference
- [x] Full orchestrator: gateway, session, router, embedder, safety guard
- [x] Domain miner with corpus loader + Merkle prover (numpy, no vector DB)
- [x] Narrative miner with OpenRouter integration
- [x] Graph store with KuzuDB persistence + in-memory fallback
- [x] Emission calculator (3 pools: traversal, quality, topology)
- [x] Metagraph watcher with registration event callbacks
- [x] Evolution system: proposals, voting, pruning, integration
- [x] K8s manifests for full stack (Kustomize)
- [x] SvelteKit frontend scaffold (Svelte 5, Tailwind 4, Drizzle)

## Next — Local Testnet (Phase 1 MVP)
- [x] Dev stack running locally (OrbStack / local Kubernetes cluster)
- [ ] Subnet registration on local subtensor
- [x] 3+ domain miner nodes with real corpora (4-node quantum mechanics graph, 10 corpus files)
- [x] Validator running full scoring loop (ScoringLoop → EmissionCalculator wired)
- [x] End-to-end traversal: gateway /enter → /hop with session lifecycle
- [ ] End-to-end traversal demo: soul token → entry → 5 hops → terminal (live on testnet)
- [ ] Wire SvelteKit frontend to gateway API
- [x] Seed graph with initial node topology (seed/topology.yaml + seed/loader.py)
- [x] Redis session persistence with in-memory fallback

## Phase 2 — Finney Testnet
- [ ] Deploy to Bittensor finney testnet via K8s
- [ ] Miner registration via IPFS manifests
- [x] Corpus integrity challenges (Merkle verification in validator loop)
- [x] WebSocket streaming for real-time hop delivery (gateway /session/{id}/live)
- [x] Session persistence in Redis (domain/narrative/session_store.py)
- [ ] Semantic drift detection
- [ ] Integration bridge window with foreshadowing
- [x] Full emission model wired to set_weights (validator → EmissionCalculator → set_weights)

## Phase 3 — Mainnet + Integrations
- [ ] Mainnet subnet registration
- [ ] bonfires.ai knowledge graph bootstrap
- [ ] Alkahest settlement layer integration
- [ ] Player dashboard (traversal ledger, epoch settlement)
- [ ] Grafana observability dashboards
