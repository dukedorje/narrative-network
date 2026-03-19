# Supervision

Erlang-style agent lifecycle management, compute scheduling, and failure recovery.

---

## Why Erlang/OTP

The knowledge graph's agent model maps naturally onto Erlang/OTP patterns:

- Agents are lightweight, isolated processes with independent state
- Agents communicate via message passing (traversals, probes, integration requests)
- Agents can fail without taking down the system
- The system needs to decide which agents run, when, and what happens when they fail

The supervision model doesn't require implementing in Erlang — it's a set of patterns applicable to any runtime. But the BEAM VM's approach to preemptive scheduling, supervision trees, and fault tolerance provides the right conceptual framework.

---

## Supervisor Trees

A **supervisor** manages a set of child agents (nodes, probes, bridge-builders). If a child agent fails or exhausts its energy, the supervisor decides: restart, escalate, or let it die.

### Supervision Strategies

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| `one_for_one` | If one child fails, only restart that child | Independent agents — isolated node recovery. Default for most cases. |
| `one_for_all` | If one child fails, restart all siblings | Tightly coupled agents — a composed subgraph where one failure invalidates the composition |
| `rest_for_one` | Restart the failed child and all children started after it | Sequential pipelines — integration pipeline where later stages depend on earlier ones |

### Tree Structure

```
Network Supervisor (one_for_one)
├── Curator Supervisor (one_for_one)
│   ├── Curator Agent A
│   ├── Curator Agent B
│   └── ...
├── Node Supervisor (one_for_one)
│   ├── Node Agent: quantum-mechanics
│   ├── Node Agent: philosophy-of-mind
│   └── ...
├── Composition Supervisor (one_for_all per composition)
│   ├── Subgraph: foundations-of-physics
│   │   ├── Node: quantum-mechanics
│   │   ├── Node: philosophy-of-science
│   │   └── Node: experimental-methodology
│   └── ...
├── Probe Supervisor (one_for_one)
│   ├── Active Probe: void-probe-embedding-region-7
│   ├── Active Probe: bridge-probe-qm-philosophy
│   └── ...
└── Integration Pipeline Supervisor (rest_for_one)
    ├── Foreshadow Worker
    ├── Bridge Builder
    └── Live Activator
```

### Failure Semantics

What does "failure" mean for different agent types?

| Agent Type | Failure Mode | Recovery |
|-----------|-------------|----------|
| **Node agent** | Corpus corruption, embedding drift, energy exhaustion | Restart with fresh corpus load; if repeated, trigger drift detection |
| **Curator agent** | Scoring error, consensus timeout | Restart; if repeated, fall back to default reward profile |
| **Probe** | External API timeout, no results | Retry with backoff; if budget exhausted, report hole as unresolvable |
| **Bridge builder** | Can't find coherent path | Report integration as blocked; escalate to curator for manual bridging |
| **Composed subgraph** | Internal coherence collapse | `one_for_all` restart of constituent nodes; if repeated, graceful decomposition |

---

## Scheduling

Not all agents need to run simultaneously. The scheduler decides which agents to activate based on:

### Scheduling Criteria

- **Pending work queue** — agents with work waiting (incoming traversals, probe results, integration requests) get priority
- **Energy level** — can the agent afford to act? No energy = yield
- **Priority class** — from the lens's energy allocation profile (hole detection vs. bridge-building vs. counterfactual checking)
- **Fairness** — prevent starvation of low-traffic nodes. Every agent gets minimum activation time per epoch.

### Preemptive Scheduling

Borrowed from BEAM: agents don't run to completion. They get a **reduction budget** (a quantum of work) and yield after exhausting it. This prevents any single agent from monopolizing compute.

- High-priority agents get larger reduction budgets
- Idle agents (no traversals, no pending probes, no integration work) yield immediately
- Agents in active integration (BRIDGE phase) get elevated priority — don't let bridge-building stall

---

## Mailbox Model

Each agent has a **mailbox** of pending work items:

- Incoming traversals
- Probe results
- Integration requests
- Counterfactual flags
- World model update notifications

### Mailbox Semantics

- Work is processed asynchronously — an agent doesn't block the network while thinking
- **Prioritized delivery**: world model updates and counterfactual flags are delivered ahead of routine traversals
- **Backpressure**: if an agent's mailbox overflows, excess work is shed (not queued forever). Shed policy:
  - Traversals: redirect to alternative nodes
  - Probes: cancel and report budget exceeded
  - Integration requests: queue (these shouldn't be shed)
  - World model updates: never shed (always delivered)

---

## Across Lenses

| Aspect | Knowledge Network | Game | Composable Network |
|--------|-------------------|------|-------------------|
| Primary supervision strategy | `one_for_one` — independent researchers | `one_for_all` within factions, `one_for_one` across | `rest_for_one` for composition pipelines |
| Scheduling emphasis | Fairness — all domains get explored | Priority — active story areas get more compute | Boundary — composition edges get priority |
| Mailbox shed policy | Aggressive on traversals, conservative on probes | Aggressive on probes, conservative on traversals | Conservative on everything at boundaries |
| Failure escalation | Slow — let agents self-recover | Fast — broken NPCs break immersion | Layered — local recovery first, composition-level if needed |

---

## Relationship to Other Physics

- **Internal Economics**: Supervision is the mechanism that *enforces* the energy model — scheduling decides who gets to spend, failure recovery decides what happens when spending goes wrong. See [internal-economics.md](internal-economics.md).
- **Hole Detection**: Probes are supervised agents with their own lifecycle and failure modes. See [hole-detection.md](hole-detection.md).
- **Observation & Integration**: The integration pipeline is a supervised sequence (rest_for_one). See [observation-and-integration.md](observation-and-integration.md).
