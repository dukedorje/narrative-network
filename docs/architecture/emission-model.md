# Emission Model

This document specifies the TAO emission model for Narrative Network (Bittensor subnet 42). Emission is the economic engine that aligns miner, validator, and governance incentives with the subnet's structural goals.

---

## Epoch Emission Split

Total epoch emission `E_epoch` is determined by the subnet's registered share of the Bittensor network emission schedule. The root network's Yuma consensus assigns this share based on validator registration and activity. The emission model treats `E_epoch` as an input — the outer loop is handled by the root network.

| Pool | Share | Recipient |
|------|-------|-----------|
| Traversal pool | 45% | Domain + Narrative miners on traversed nodes |
| Quality pool | 30% | Validators (20%) + top-scoring miners (10%) |
| Topology pool | 15% | All live nodes, weighted by betweenness centrality |
| Proposal reserve | 10% | Locked; disbursed as returned bonds + governance |

Within each pool, the Domain/Narrative miner split is:

| Pool | Domain miner | Narrative miner |
|------|-------------|-----------------|
| Traversal pool | 35% | 65% |
| Quality bonus | 25% | 75% |

Narrative miners carry the heavier creative and synthesis burden, so they receive the larger share of per-hop and quality rewards. Domain miners earn a stable base reflecting corpus maintenance work.

---

## Traversal Pool (45%)

For each completed `NarrativeHop` in an epoch, only the miner selected by the orchestrator for the actual session earns the traversal credit — runners-up do not. Each hop is weighted by its `quality_score` relative to the epoch total.

```python
def traversal_pool_epoch(hops, E_epoch, TRAVERSAL_SHARE=0.45, DOMAIN_SPLIT=0.35):
    pool = E_epoch * TRAVERSAL_SHARE
    domain_pool = pool * DOMAIN_SPLIT
    narrative_pool = pool * (1 - DOMAIN_SPLIT)
    total_quality = sum(h.quality_score for h in hops) or 1.0
    rewards = {}
    for hop in hops:
        w = hop.quality_score / total_quality
        rewards[hop.domain_miner_uid] = rewards.get(hop.domain_miner_uid, 0) + domain_pool * w
        rewards[hop.narrative_miner_uid] = rewards.get(hop.narrative_miner_uid, 0) + narrative_pool * w
    return rewards
```

`hops` is the list of all completed hops in the epoch. Each hop carries:
- `quality_score` — validator-assigned score for this hop
- `domain_miner_uid` — the miner serving the node's corpus
- `narrative_miner_uid` — the miner that generated the narrative transition

Key insight: quality-weighting inside the traversal pool means high-quality nodes on high-traffic paths compound rewards. A miner improving average score from 0.65 to 0.80 on a well-traversed node earns significantly more than the absolute score increase suggests.

---

## Quality Pool (30%)

The quality pool splits 66.7% to validators and 33.3% as a miner bonus for top-quartile performers.

- **Validator share (66.7%):** Proportional to the number of valid scores submitted in the epoch. Validators that go offline for an epoch earn zero quality pool income.
- **Miner bonus (33.3%):** Top-quartile miners by average score receive a bonus proportional to their score. The cutoff is recalculated each epoch from the live distribution.

```python
def quality_pool_epoch(scored_responses, E_epoch, QUALITY_SHARE=0.30, VALIDATOR_CUT=0.667, TOP_QUARTILE=0.25):
    pool = E_epoch * QUALITY_SHARE
    validator_pool = pool * VALIDATOR_CUT
    miner_bonus_pool = pool * (1 - VALIDATOR_CUT)

    # Validators: proportional to number of valid scores submitted
    validator_score_counts = {}
    for resp in scored_responses:
        if resp.score is not None:
            uid = resp.validator_uid
            validator_score_counts[uid] = validator_score_counts.get(uid, 0) + 1
    total_validator_scores = sum(validator_score_counts.values()) or 1
    validator_rewards = {
        uid: validator_pool * (count / total_validator_scores)
        for uid, count in validator_score_counts.items()
    }

    # Miners: top-quartile bonus proportional to score
    miner_avg_scores = {}
    miner_score_counts = {}
    for resp in scored_responses:
        if resp.score is not None:
            uid = resp.miner_uid
            miner_avg_scores[uid] = miner_avg_scores.get(uid, 0) + resp.score
            miner_score_counts[uid] = miner_score_counts.get(uid, 0) + 1
    miner_avg_scores = {
        uid: total / miner_score_counts[uid]
        for uid, total in miner_avg_scores.items()
    }
    sorted_scores = sorted(miner_avg_scores.values())
    cutoff_index = int(len(sorted_scores) * (1 - TOP_QUARTILE))
    cutoff = sorted_scores[cutoff_index] if cutoff_index < len(sorted_scores) else float('inf')
    top_miners = {uid: score for uid, score in miner_avg_scores.items() if score >= cutoff}
    total_top_score = sum(top_miners.values()) or 1
    miner_rewards = {
        uid: miner_bonus_pool * (score / total_top_score)
        for uid, score in top_miners.items()
    }

    return validator_rewards, miner_rewards
```

The bonus creates competition even at low-traffic nodes. An excellent response on an obscure node still earns meaningfully if it pushes a miner into the top quartile for the epoch.

---

## Topology Pool (15%)

The topology pool distributes based on betweenness centrality — the fraction of all shortest paths in the graph that pass through a given node. This measures structural importance independent of current traffic volume.

Edge weights in the graph store use `weight = 1 / edge_weight` for distance computation, so frequently traversed edges are treated as shorter paths.

```python
def topology_pool_epoch(graph_store, live_node_ids, E_epoch, TOPOLOGY_SHARE=0.15):
    import networkx as nx

    pool = E_epoch * TOPOLOGY_SHARE

    # Build directed graph from graph store edges
    G = nx.DiGraph()
    G.add_nodes_from(live_node_ids)
    for edge in graph_store.get_edges(nodes=live_node_ids):
        # Use inverse weight as distance so high-weight edges are "shorter"
        distance = 1.0 / edge.weight if edge.weight > 0 else float('inf')
        G.add_edge(edge.source_id, edge.target_id, weight=distance)

    # Compute betweenness centrality (normalized by default)
    centrality = nx.betweenness_centrality(G, weight='weight', normalized=True)

    # Restrict to live nodes only
    live_centrality = {uid: centrality.get(uid, 0.0) for uid in live_node_ids}
    total_centrality = sum(live_centrality.values()) or 1.0

    rewards = {
        uid: pool * (c / total_centrality)
        for uid, c in live_centrality.items()
        if c > 0
    }
    return rewards
```

Key property: newly integrated bridge nodes earn meaningful topology rewards from day one, before player discovery drives traffic. The topology pool rewards structural contribution — connecting otherwise-distant regions of the graph — not just popularity or traversal volume.

A node that serves as a bridge between two major clusters will appear on many shortest paths and earn consistently even during low-traffic periods.

---

## Proposal Reserve (10%)

The proposal reserve is net-zero over time. It accumulates bonds from governance proposals and disburses them according to proposal outcomes.

| Outcome | Bond disposition |
|---------|-----------------|
| Successful proposal (quorum reached, enacted) | Bond returned + 1.05x multiplier from reserve |
| Lapsed proposal (insufficient quorum, not slashed) | 95% of bond returned; 5% stays in reserve |
| Slashed proposal (fraudulent corpora, spam detected) | Full bond forfeited to reserve; redistributed to detecting validators |

The 1.05x multiplier on successful proposals is the incentive to submit well-researched, high-quality proposals. The 5% lapse fee discourages low-effort proposals without making governance prohibitively risky. Slash conditions are restricted to clearly fraudulent submissions — governance disagreement alone is not slashable.

Detecting validators that flag and confirm a fraudulent proposal share the slashed bond proportional to their confirmation stake.

---

## Key Economic Properties

### 1. Traffic concentration effects

At low Gini coefficient (uniform traffic across nodes), peripheral nodes earn a meaningful traversal share. At high Gini (0.8+), hub traversal earnings dominate, but bridge node topology earnings remain robust because betweenness centrality is structural, not traffic-dependent. The two pools therefore hedge each other: popular hubs earn more from traversal, structurally important bridges earn more from topology.

### 2. Quality score compounding

A miner at 0.80 average score when the epoch mean is 0.65 earns approximately 23% more per hop via quality weighting, plus qualifies for the top-quartile quality bonus. Over multiple epochs: higher earnings enable better hardware, which enables higher scores, which produces convex returns. This is intentional — the subnet benefits from concentration of high-quality corpus and narrative generation capacity.

### 3. Validator incentive stability

Validators earn proportional to valid scores submitted. Going offline for an epoch yields zero quality pool income. Validators earn approximately 2x per-score income compared to top-quartile miners (66.7% vs 33.3% of quality pool, before miner count effects). This spread is appropriate: submitting a valid score requires running inference and maintaining metagraph state, which is more expensive than serving a single hop.

### 4. E_epoch scaling

The subnet's emission share rises with consistent validator activity and demonstrated miner quality. It falls if validators defect, metagraph state goes stale, or the subnet fails to produce the volume of scored responses the root network expects. The emission model treats `E_epoch` as input — operators should treat validator uptime and metagraph health as the primary levers for subnet-level emission share.

---

## Arkhai/Alkahest Integration Points

The emission model maps naturally onto Alkahest's escrow and arbiter pattern, providing on-chain attestation for every economic event via EAS (Ethereum Attestation Service).

**Traversal credits as escrow obligations**
Each completed hop creates an escrow obligation. The escrow releases TAO to the winning miner when the validator's arbiter confirms the quality score meets threshold. The arbiter can be a simple threshold check (score >= 0.5) or a more sophisticated multi-validator consensus.

**Natural language agreements for domain manifests**
Miners' domain manifests — the description of what corpus they maintain and what nodes they serve — can be expressed as Alkahest obligations with algorithmic arbiters checking corpus integrity. The arbiter verifies that the miner's actual corpus matches the manifest before releasing topology rewards.

**Proposal bonds as Alkahest escrows**
Governance proposal bonds are locked via Alkahest escrow contracts. The arbiter is the validator set: slash decisions, quorum confirmations, and lapse rulings are all resolvable on-chain by the validators that participated in the epoch when the proposal was evaluated.

**Attestation trail**
Every economic event — hop completion, score submission, topology reward, proposal bond outcome — produces an EAS attestation. This creates an auditable, permissionless record of subnet economics that external tools can query without access to Bittensor's internal metagraph state.
