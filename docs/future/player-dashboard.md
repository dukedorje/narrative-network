# Player Dashboard

Bittensor Subnet 42 — Narrative Network

---

## Overview

The player dashboard is the game layer — the surface where economic reality and narrative experience are made legible together. Every number on the screen corresponds to a traversal, a scored passage, or a structural contribution. The design goal is to make those correspondences visible without reducing the experience to a spreadsheet.

The dashboard exists within a session. A session is a single traversal sequence: one player, one starting node, one sequence of hops through the graph. The dashboard tracks what happened in that session, what it earned, and how it sits relative to other sessions in the same epoch.

---

## Session Identity

The header ties player session identity to epoch context. A returning player sees their session identifier — a short hex string, e.g., 0x7f3a — alongside the current epoch number. SN-42 (the subnet identifier) is always visible for treasury context: the player knows which network they are operating in and what the emission source is.

Returning players see their accumulated folio carried across epochs. The folio is the longitudinal record — the sum of all prior session contributions, quality scores, and graph reinforcements. It is the player's history in the network made tangible.

---

## Current Position

The top-left panel shows where the player is in the graph, expressed in narrative terms.

The chapter title comes from the active node's story — a prose heading derived from the narrative passage at that node, not a dry node identifier. A player does not see "n42-cluster-07." They see the title of the passage they are currently inside.

Below the title: depth count (how many hops from the session's origin node) and the path trail. The path trail renders as a sequence of pill tokens — one per visited node. Visited nodes appear muted and recessed. The current node is solid ink. The trail communicates trajectory without requiring the player to reconstruct it from memory.

---

## Traversal Ledger

The traversal ledger is the core of the dashboard. It is a log of every hop in the session, rendered as a table where each row is one traversal.

Each row contains:
- Hop number
- Route: from-node to to-node, expressed in the prose titles of both nodes
- Excerpt: a short pull from the narrative passage at the destination node — the specific text that earned the quality score
- Quality score with an inline bar visualization
- Earnings for that hop in TAO

The excerpt is the design's load-bearing element. It ties the financial instrument back to the story. The player sees the passage that earned the credit. Quality is not an abstraction — it is legible in the text.

Hops that fall in the top quartile of quality scores for that epoch carry a TOP QUARTILE badge. This surfaces the player's strongest contributions without requiring them to compute their relative standing.

Topology accrual appears as a separate row at the bottom of the ledger. It is epoch-level and structural — not tied to any single hop — so it is rendered distinctly from traversal rows. The row shows the edge or edges reinforced, the centrality contribution, and the topology pool accrual for the epoch so far.

---

## Session Summary

The right column is a summary view aggregated across the full session.

The primary figure is the session total in TAO — a large number that anchors the column. Below it, a pool breakdown splits the total into traversal earnings and topology accrual. The quality bonus line is marked as pending until epoch close, when it settles.

Session metrics below the pool breakdown:
- Mean quality score across all hops
- Top-quartile hop count
- Depth (total hops in the session)

Graph contribution is made explicit: the dashboard lists the specific edges the player reinforced during the session. A bridge reinforcement — where the player's traversal strengthened an edge connecting two otherwise weakly-connected clusters — is called out specifically, e.g., "bridge: n3 to n7." This makes the player's structural contribution legible, not just their quality score.

Path rank is computed by the orchestrator against all sessions in the current epoch and displayed as a percentile, e.g., "top 8%." This contextualizes the session's performance without requiring the player to know the full distribution.

---

## Pending vs Settled

Traversal pool credits accrue in real time during a session. They are visible immediately but marked as pending until epoch close.

Pending amounts render in amber. Settled amounts render in teal. The color distinction communicates finality. A player looking at their ledger during an active epoch sees amber numbers that represent accrued but not yet finalized earnings. At epoch close, those numbers shift to teal.

Quality bonuses settle at epoch close because they are computed across the full epoch's scoring distribution. A quality bonus that appears to be accruing during the session is an estimate; the final amount depends on how all other sessions in the epoch scored.

---

## Future Views

### Epoch Settlement View

At epoch close, the ledger "prints." Row values freeze. Pending amber figures shift to settled teal. A timestamp marks the settlement block. The transition is visible — the dashboard communicates that finalization has occurred, not just that numbers changed.

The settlement view is the receipt. It is the permanent record of what that session contributed and what it earned.

### Multi-Epoch Folio

The folio view is longitudinal. It spans all of a player's sessions across epochs and presents:
- Path history: a visual or tabular record of traversal sequences across sessions
- Cumulative graph contribution: the total set of edges the player has reinforced or created
- Quality score evolution: how the player's mean quality score has changed over time

The folio is a living autobiography in the graph. It is the player's authorship record — not just what they earned but what they built, what knowledge paths they walked, and how their navigation of the network has evolved.

### Node Intelligence Panel

Clicking any hop row in the traversal ledger expands a Node Intelligence Panel for that hop. The panel surfaces:
- Groundedness score for the passage at that node (how well the passage is anchored in the source corpus)
- Coherence score (internal narrative consistency)
- Edge utility score (the structural value of the traversal edge)
- Miner UID for the narrative miner that authored the passage
- Competing miners' scores for the same node in that epoch

The panel turns the validator scoring process from a black box into a transparent breakdown. A player can see exactly why a hop scored as it did and how it compared to competing passages. This is both informational and educational — players learn what high-quality synthesis looks like by examining the scoring components of their best and worst hops.

---

## Mutatable Interface

The dashboard is not static. It reflects live network state.

The graph visualization updates in real time. Edges thicken as other players traverse the same paths during the epoch. New nodes fade in during integration — a new miner's node becoming visible as it passes incubation. Nodes undergoing pruning (edge weights decaying below threshold) flicker as they approach removal from the active graph.

The interface mutates based on shared game state. A player watching the graph during an active epoch sees the network breathing — traffic concentrating on high-quality paths, new structure emerging at the periphery, old structure fading at the edges.

The session dashboard is the local view. The live graph is the global view. Together they situate the player's individual session within the larger movement of the network.
