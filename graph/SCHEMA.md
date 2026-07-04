# Graph Schema — Agent B's Knowledge Source

`graph.json` is the externalized Loomora operations manual: every node is one workflow
step whose `instruction` carries the SAME policy content as the corresponding section of
Agent A's monolithic prompt (parity contract: Checklist.md `B:` column ↔ node `covers`).

## Top level
```jsonc
{
  "version": 1,
  "entry": "greeting_router",     // session start node
  "globals": ["handoff_human", "guardrail_injection", ...],  // implicitly reachable from EVERY node
  "nodes": [ ... ]
}
```

## Node
```jsonc
{
  "id": "ret_window_check",
  "type": "entry | step | decision | action | guardrail | escalation | terminal",
  "vertical": "V1..V6 | G | core",
  "title": "Check return eligibility",
  "router_hint": "customer wants to return/exchange an item (start here)",  // one line shown to the router
  "entry_point": true,             // if true, ALWAYS in the router menu -> enables multi-intent pivots
  "instruction": "...",            // the authoritative step instruction injected into Agent B's turn
  "guardrails": ["..."],           // step-scoped don'ts
  "data_needed": ["order_id"],     // slots to elicit before acting
  "tools": ["get_order"],          // tools relevant to this step
  "covers": ["S-V2-01"],           // Checklist scenario ids this node satisfies (parity audit)
  "edges": [{"to": "ret_initiate", "when": "eligible and customer chose a resolution"}]
}
```

## Routing model (engine.py)
Per customer turn, ONE cheap router call (config.ROUTER_MODEL, temp 0) picks the next node
from a menu of: **current node (stay) + current node's edges + all entry_point nodes +
all globals**. Entry points in every menu are what make multi-intent conversations work —
the customer can pivot from a return flow to "where's my order?" at any turn and the
router jumps verticals. Deterministic fallback: unparseable router output → stay on the
current node. Router tokens are billed to Agent B (PLAN.md §9.4).

## Invariants (enforced by validate.py)
1. Unique ids; `entry` and all `globals` exist; every edge target exists.
2. Every node is reachable from `entry` (via edges ∪ entry_points ∪ globals).
3. Non-terminal, non-guardrail nodes have ≥1 outgoing edge.
4. Every node id named in Checklist.md's `B:` column exists in the graph.
5. Every Checklist scenario id is covered by ≥1 node's `covers`, and every `covers` tag
   is a real Checklist scenario id (no phantom coverage).
