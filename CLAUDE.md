# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Narrative Network is a Bittensor subnet — a living knowledge graph with comparative attestation. It has two distinct codebases in one repo:

1. **SvelteKit web app** (TypeScript/Svelte 5) — gateway UI for traversing the knowledge graph
2. **Python subnet** — Bittensor validator, miners, orchestrator, graph evolution, and scoring

## Commands

### Web App (TypeScript/SvelteKit)
```bash
npm run dev              # Dev server
npm run build            # Production build
npm run check            # svelte-check + TypeScript
npm run lint             # Prettier + ESLint
npm run format           # Auto-format with Prettier
npm run test:unit        # Vitest (run and watch)
npm run test:unit -- --run  # Vitest single run
npm run test:e2e         # Playwright e2e tests
npm run storybook        # Storybook on port 6006
```

### Database (Drizzle + PostgreSQL)
```bash
npm run db:push          # Push schema to DB
npm run db:generate      # Generate migrations
npm run db:migrate       # Run migrations
npm run db:studio        # Drizzle Studio GUI
```
Requires `DATABASE_URL` env var.

### Python Subnet
```bash
uv sync                          # Install dependencies
uv sync --extra dev              # With dev deps (pytest, ruff, mypy)
uv run pytest                    # Run tests (tests/ directory)
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run python -m subnet.validator  # Run validator
uv run python -m domain.miner     # Run domain miner
uv run python -m domain.narrative.miner  # Run narrative miner
```
Entry points (after install): `narrative-validator`, `narrative-domain-miner`, `narrative-miner`, `narrative-gateway`

Requires Python >= 3.12. Uses Bittensor SDK v10 (`bt.Wallet`, `bt.Subtensor`, etc — capitalized).

### Kubernetes
```bash
kubectl apply -k k8s/            # Deploy full stack
```

## Architecture

### Python Package Structure

**`subnet/`** — Core Bittensor protocol
- `protocol.py` — Wire protocol: `KnowledgeQuery` and `NarrativeHop` synapses, `WeightCommit` dataclass
- `validator.py` — Scores miners on 4 axes, sets weights via Yuma Consensus
- `reward.py` — Scoring functions: traversal (0.40), quality (0.30), topology (0.15), corpus (0.15)
- `config.py` — All tunable constants + `SubnetConfig` class. Env override via `AXON_` prefix (e.g. `AXON_NETUID=1`)
- `graph_store.py` — In-memory graph with optional KuzuDB persistence. Brandes betweenness centrality, edge decay, traversal logging
- `emissions.py` — Three emission pools (Traversal, Quality, Topology) with per-pool normalization (rank/linear/softmax). `EmissionCalculator` produces final weight vector
- `metagraph_watcher.py` — Async background poller with `AxonCache`, fires `RegistrationEvent` callbacks on miner changes

**`domain/`** — Miner implementations
- `miner.py` — Domain miner: corpus chunk retrieval via numpy cosine similarity + Merkle proof responses
- `corpus.py` — `CorpusLoader` (chunking, SentenceTransformer embedding, pickle cache) + `MerkleProver` (SHA-256 binary Merkle tree with inclusion proofs). No vector DB — numpy in-memory
- `manifest.py` — `DomainManifest` dataclass (IPFS-pinned domain declaration)
- `narrative/miner.py` — Narrative miner: generates hop text via OpenRouter (OpenAI-compatible API), Redis-backed session context
- `narrative/prompt.py` — Persona catalogue + prompt builder for hop generation
- `narrative/session_store.py` — Redis session store with in-memory fallback

**`orchestrator/`** — Gateway and session management
- `gateway.py` — FastAPI app: `POST /enter`, `POST /hop`, `GET /session/{id}`, `WS /session/{id}/live`, `GET /healthz`
- `session.py` — `OrchestratorSession`: manages traversal lifecycle, sends KnowledgeQuery/NarrativeHop via dendrite
- `router.py` — Entry-node ranking by domain centroid similarity, narrative miner resolution
- `embedder.py` — SentenceTransformer wrapper (`all-mpnet-base-v2`, 768-dim)
- `safety_guard.py` — Path cycle prevention, word count enforcement

**`evolution/`** — Graph evolution (node lifecycle)
- `proposal.py` — `NodeProposal` with on-chain commitment, `ProposalSubmitter` (validate → bond → commit)
- `voting.py` — Stake-weighted voting: `VotingEngine` with quorum + approval threshold
- `pruning.py` — Three-phase pruning state machine: WARNING → DECAYING (aggressive edge decay) → COLLAPSED
- `integration.py` — Three-phase node onboarding: FORESHADOW → BRIDGE (edge ramp) → LIVE

**`src/`** — SvelteKit 5 web app
- Svelte 5, Tailwind CSS 4, mdsvex, Paraglide (i18n)
- Drizzle ORM with PostgreSQL (`src/lib/server/db/`)
- Storybook for component development (`src/stories/`)

**`k8s/`** — Kubernetes manifests (Kustomize)
- Gateway (HPA 2-5), Validator (StatefulSet + PVC), Domain/Narrative miners, Frontend, Redis, IPFS, Ingress

### Key Design Decisions
- **No vector DB service**: Domain miners use numpy cosine similarity in-process. Corpus fits in memory
- **OpenRouter for LLM**: Narrative miners call OpenRouter API (no GPU infrastructure). Set `OPENROUTER_API_KEY` env var
- **KuzuDB embedded**: Graph DB runs in-process on validator/gateway pods, persisted via PVC
- **Config via env**: All `subnet/config.py` constants overridable with `AXON_` prefix for K8s ConfigMap injection

### Key Concepts
- **Knowledge graph**: Nodes are miner-owned knowledge domains; edges are weighted traversal paths
- **Session**: A player traverses the graph via NarrativeHop synapses; miners compete to narrate each hop
- **Scoring**: Four axes — traversal relevance, narrative quality, topology importance, corpus integrity
- **Edge dynamics**: Reinforced by quality traversals, multiplicative decay each epoch
- **Emission pools**: Traversal (45%), Quality (30%), Topology (15%), Reserve (10%)
- **Node lifecycle**: Proposal → Voting → Incubation → Integration (foreshadow/bridge/ramp) → Live → (Pruning if underperforming)
- **Subnet ID**: 42 (`NETUID` in `subnet/__init__.py`)

### Test Configuration
**Vitest** (two projects in `vite.config.ts`):
- **client**: Browser tests via Playwright, matches `src/**/*.svelte.{test,spec}.{js,ts}`, excludes `src/lib/server/`
- **server**: Node environment, matches `src/**/*.{test,spec}.{js,ts}`, excludes `.svelte.` test files
- All tests require assertions (`expect.requireAssertions: true`)

**Pytest**: asyncio_mode auto, testpaths = tests/

### Linting
- **Ruff**: line-length 100, target Python 3.12, select rules E/F/I/N/W
- **ESLint + Prettier**: TypeScript + Svelte config
