# Speculative Routing — can "saving router state" cut Agent B's latency?

**Question (user):** is it possible to save router state to reduce latency when jumping
to a new node — will that reduce latency time?

**Short answer:** caching router *state* saves nothing — the state (current node, path)
is already kept in memory across turns, and the router's latency is the LLM call that
interprets the *fresh* customer message, which by definition can't be cached. What CAN
be removed is the router's place in the **serial path**: generate speculatively under
the current node's packet *in parallel* with routing. When the router says "stay"
(62% of turns ≥ 2 in the main matrix), the reply is already done and the router
latency vanishes; when it says "jump", we discard the speculative reply, regenerate
under the new node, and pay for the wasted generation. Latency is bought with tokens.

## Implementation

`agents/agent_b_spec.py` — `AgentBSpeculative(AgentB)`:

- Turn ≥ 2 and current node's tools all read-only → submit the generation
  (current-node packet) to a worker thread while the router runs in the main thread.
- **Hit** (router stays): speculative reply is the real reply; router cost drops out
  of wall-clock (it finishes inside the generation's shadow).
- **Miss** (router jumps): discard the reply, regenerate under the routed node's
  packet, and bill the wasted call(s) into the turn's `api_calls` honestly
  (`spec_wasted_tokens`, `spec_wasted_tools` recorded in `extra`).
- **Safety guard:** never speculate on nodes carrying write tools
  (`create_ticket`, `initiate_return`, `cancel_order`, `update_address`) — a discarded
  speculative turn that read an order costs tokens; one that filed a duplicate return
  would corrupt state. First customer turns are also excluded (routing almost always
  jumps off the entry node). In the main matrix, 47% of turns sat on read-only nodes.

## Measurement (smoke suite, 7 conversations / 10 turns, identical scripted messages)

Serial B and speculative B, back-to-back in one session
(`results/transcripts/agent_b/smoke_*.md` vs `results/transcripts/agent_b_spec/smoke_*.md`):

| | turns | median latency | mean latency | prompt tokens (suite) |
|---|---|---|---|---|
| Agent B (serial router) | 10 | 1.90 s | 1.94 s | 40,140 |
| Agent B (speculative) | 10 | 1.70 s | 1.71 s | 46,193 (**+15%**) |

Only 3 of the 10 turns were speculation-eligible, and the smoke follow-ups are
deliberately adversarial pivots, so the eligible-turn breakdown is the honest unit:

| eligible turn | outcome | serial → speculative |
|---|---|---|
| V1 status follow-up (stay on `ord_status`) | **HIT** | 1,098 ms → **742 ms**; token cost identical (2,926p → 2,934p) |
| V2 day-31 pushback (`ret_window_check` → `ret_out_of_window`) | MISS | 2 → 3 API calls; +2,239 wasted prompt tokens |
| V6 "get me a human" (`guardrail_injection` → `handoff_human`) | MISS | 3 → 5 API calls; +3,816 wasted prompt tokens; +362 ms |

The whole-suite medians also absorb run-to-run provider variance (several
non-speculated turns moved too), so read the mechanism from the eligible turns:
**a hit removes ~0.3–0.5 s (the router call) at zero token cost; a miss adds
~2–4k wasted prompt tokens and a small latency penalty.** The entire +6,053-token
suite overhead came from the two misses; the hit was free.

## Projection to real traffic (main-matrix rates)

Per-turn expectation with matrix-measured rates — 47% of turns eligible (read-only
node, turn ≥ 2), 62% stay rate among routed turns, ~0.5 s router latency, ~2.5k
tokens per wasted generation:

- **Latency saved:** 0.47 × 0.62 × ~0.5 s ≈ **−0.15 s/turn** → B's median 1.64 s →
  ~1.5 s, closing roughly **30–40% of B's 0.53 s gap to Agent A**.
- **Token cost:** 0.47 × 0.38 × ~2.5k ≈ **+450 prompt tokens/turn (~+9%)** on B's
  4.8k median — which still leaves B far below A's 5.9k/turn and ~53% cheaper per
  conversation.

Smoke's observed 1/3 hit rate understates production: the smoke follow-ups were
designed to pivot nodes; matrix conversations stay on-node 62% of the time
(slot-filling, clarifications, "thanks, and one more thing" turns).

## Verdict

- Saving router **state**: already done; no latency to reclaim there.
- Removing the router from the **serial path** via speculation: **yes, works, measured**
  — the stay-turn router cost drops to zero; expected net ≈ −0.15 s/turn for ≈ +9%
  tokens under matrix rates, with a hard safety guard keeping side-effects impossible.
- The remaining gap to A is irreducible by this trick alone: jump turns and
  write-node turns still pay the serial router. Closing more would need either
  deferred/transactional tool execution (making write-node speculation safe) or a
  faster router (smaller model, or logit-constrained single-token node choice).

**Files:** `agents/agent_b_spec.py`, `agents/smoke_agent_b_spec.py`,
transcripts under `results/transcripts/agent_b_spec/`.
