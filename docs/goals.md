
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
- [ ] Dev stack running locally (minikube / local Kubernetes cluster)
- [ ] Subnet registration on local subtensor
- [ ] 3+ domain miner nodes with real corpora
- [ ] Validator running full scoring loop (connect ScoringLoop to emissions)
- [ ] End-to-end traversal demo: soul token → entry → 5 hops → terminal
- [ ] Wire SvelteKit frontend to gateway API
- [ ] Seed graph with initial node topology (nodes.yaml or script)

## Phase 2 — Finney Testnet
- [ ] Deploy to Bittensor finney testnet via K8s
- [ ] Miner registration via IPFS manifests
- [ ] Corpus integrity challenges (Merkle verification in validator loop)
- [ ] WebSocket streaming for real-time hop delivery
- [ ] Session persistence in Redis (replace in-memory fallback)
- [ ] Semantic drift detection
- [ ] Integration bridge window with foreshadowing
- [ ] Full emission model wired to set_weights

## Phase 3 — Mainnet + Integrations
- [ ] Mainnet subnet registration
- [ ] bonfires.ai knowledge graph bootstrap
- [ ] Alkahest settlement layer integration
- [ ] Player dashboard (traversal ledger, epoch settlement)
- [ ] Grafana observability dashboards
