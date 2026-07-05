# PLAN.md — Graph-RAG vs Monolithic-Prompt Agent: Token & Compute Efficiency Study

> **Research question:** For a multi-turn customer-support workflow, does an agent driven by a
> Graph-RAG knowledge source (small system prompt + per-turn retrieval of only the relevant
> workflow nodes) consume meaningfully fewer tokens and less compute than an agent carrying a
> monolithic, all-inclusive system prompt — **without losing conversation quality**?

---

## 1. Hypothesis & What We Measure

### 1.1 The problem being modeled
In a conventional agent, the system prompt must contain *every* policy, workflow, edge case and
guardrail up front. That fixed block is re-sent (and re-attended-to) on **every turn**, and the
chained conversation history grows on top of it. Consequences: prompt-token cost grows linearly
per turn with a large constant, latency climbs, and instruction-following degrades as the model's
attention is spread across thousands of tokens of mostly-irrelevant instructions ("lost in the
middle").

### 1.2 The proposed remedy
Externalize the workflow into a **directed knowledge graph**. Each node holds the instructions,
data requirements and guardrails for exactly one step of one support flow; directed edges encode
the legal transitions (including escalation and guardrail jumps). Per turn, the agent receives:

1. A **crisp, static system prompt** (persona, tone, global guardrails, how to use node packets).
2. A **node packet** — only the current node's instructions + a menu of its outgoing edges.

The fixed per-turn instruction overhead becomes O(one node) instead of O(entire policy manual).

### 1.3 Hypotheses
- **H1 (tokens):** Agent B's per-turn prompt tokens and cumulative conversation tokens are
  significantly lower than Agent A's (target: ≥40% reduction in per-turn prompt tokens).
- **H2 (latency):** Agent B's time-to-first-token / total response latency is lower or equal.
- **H3 (quality):** Agent B's Q-C score is ≥ Agent A's (no quality regression; possibly an
  improvement on long conversations where A degrades).
- **H4 (degradation curve):** A's quality/latency degrade faster than B's as turn count grows.

### 1.4 Primary metrics (per turn, per conversation, per agent)
| Metric | Source | Notes |
|---|---|---|
| `prompt_tokens`, `completion_tokens`, `total_tokens` | Groq API `usage` object | Ground truth for compute |
| `latency_ms` (wall clock, request→response) | harness timer | Report median + p90; network noise mitigated by repetitions |
| `cumulative_tokens` at turn *n* | derived | The context-growth curve — the headline chart |
| **B-side overhead** (`router_tokens`, `retrieval_calls`) | harness | **Counted against Agent B's totals — no hidden costs** |
| `turns_to_resolution`, `resolved`, `escalated_to_human` | harness + judge | Effectiveness |
| **Q-C score** (0–100 composite) | blind LLM judge | See §10 |
| Full transcripts | harness | Stored per conversation for manual review |

---

## 2. Key Decisions & Assumptions (made to keep moving; flag to change)

| # | Decision | Rationale |
|---|---|---|
| D1 | **Language/stack: Python 3.11+**, `groq` SDK, SQLite, `networkx` (validation only), `matplotlib/plotly` | Fastest path; SQLite = zero-infra tabular DB |
| D2 | **Agent model: `meta-llama/llama-4-scout-17b-16e-instruct`** on Groq — *identical* for Agent A and Agent B, temperature 0.3, same max_tokens. *(Revised 2026-07-05: originally `llama-3.3-70b-versatile`, but free-tier limits rule it out — 70B is capped at 100k tokens/day and one Agent A conversation ≈ 28k; 8B-instant's 6k TPM can't even carry Agent A's ~6.3k-token request. Scout: 30k TPM / 500k TPD / 1k requests-day. The 1k RPD budgets the M7 matrix — plan 2 runs/scenario or a two-day split. Same-model comparison still isolates the architecture variable.)* | Same-model comparison isolates the architecture variable |
| D3 | **Customer simulator model: `llama-3.1-8b-instant`** with fixed persona scripts | Cheap, fast, deterministic-ish adversary; identical scripts for both agents |
| D4 | **Judge model: `openai/gpt-oss-120b`** (on Groq) — different family than the agents | Reduces same-family self-preference bias in Q-C scoring |
| D5 | **Graph storage: versioned JSON in-repo** (`graph/graph.json`), traversed by a deterministic engine + one tiny LLM router call per turn | "Don't overcomplicate" — no vector DB / Neo4j needed; the graph is small enough for exact traversal. Router cost is honestly billed to B |
| D6 | **Conversations are simulated** (LLM plays the customer from scripted goals), 3 runs per scenario per agent | Matches the "run simulations" objective; repetition tames variance |
| D7 | **Voice is out of scope for v1** (noted in repo name) — future work; token savings matter even more for voice latency budgets | Keep v1 falsifiable and small |
| D8 | Both agents get the **same DB tool** (`lookup(...)` functions over SQLite) | Data access parity |

**Open questions for the user (defaults in bold, proceeding with them):**
1. Model choice OK? (**D2/D3/D4 above**) — swappable via one config file.
2. Runs per scenario: **3** (≈ 45 scenarios × 2 agents × 3 runs ≈ 270 conversations). Reduce if Groq rate limits bite.
3. Any preference for the store's product domain beyond "online clothes store"? (**Fictional brand "Loomora" below**.)

---

## 3. Repository Layout

```
Graph-RAG-Voice-Tokens/
├── PLAN.md                      ← this file
├── Checklist.md                 ← scenario coverage checklist (§7) — the parity contract
├── README.md
├── requirements.txt
├── config.py                    ← models, temps, run counts, paths (single source of truth)
├── .env                         ← GROQ_API_KEY (already present; never committed)
│
├── db/
│   ├── schema.sql               ← tabular records DB schema (§5)
│   ├── seed.py                  ← deterministic seed data generator
│   └── store.db                 ← generated SQLite database
│
├── agents/
│   ├── prompts/
│   │   ├── agent_a_system.md    ← the monolithic prompt (stored verbatim, as required)
│   │   └── agent_b_system.md    ← the crisp prompt (stored verbatim, as required)
│   ├── tools.py                 ← shared DB lookup tools (identical for A and B)
│   ├── agent_a.py               ← monolithic-prompt agent
│   └── agent_b.py               ← graph-directed agent (uses graph/engine.py)
│
├── graph/
│   ├── SCHEMA.md                ← node/edge type documentation
│   ├── graph.json               ← the Graph-RAG knowledge source (§8)
│   ├── engine.py                ← session state, router, node-packet composer
│   └── validate.py              ← structural checks: reachability, dead ends, coverage vs Checklist.md
│
├── simulation/
│   ├── personas.json            ← customer personas (calm, terse, angry, confused, adversarial)
│   ├── scenarios.json           ← machine-readable version of Checklist.md scenarios
│   ├── customer.py              ← LLM customer simulator
│   └── run_experiments.py       ← the harness: runs scenario × agent × repetition matrix
│
├── analysis/
│   ├── parity_audit.py          ← automated no-bias check (§9)
│   ├── qc_judge.py              ← blind LLM-judge Q-C scorer (§10)
│   └── visualize.py             ← charts (§11)
│
├── results/
│   ├── transcripts/
│   │   ├── agent_a/S{id}_run{n}.md + .jsonl
│   │   └── agent_b/S{id}_run{n}.md + .jsonl
│   ├── metrics/turns.csv        ← one row per turn (all metrics of §1.4)
│   ├── metrics/conversations.csv
│   └── qc/scores.jsonl
│
└── REPORT.md                    ← final write-up with embedded charts
```

---

## 4. The Scenario World — "Loomora", an Online Clothing Store

A mid-size online-only apparel brand. Ships domestically in 3–5 business days, internationally
in 7–14. 30-day return window (unworn, tags attached; final-sale items excluded). Free returns
for store credit; refunds to original payment minus nothing (free return shipping over $50,
else $4.99 label fee). Loyalty tiers: Basic / Silver / Gold (Gold gets free expedited shipping
and a 40-day return window). Support hours for humans: 9am–6pm ET weekdays — the bots run 24/7
and hand off to a human queue outside hours (callback ticket).

### 4.1 Support verticals (deliberately few, per instructions)
| Vertical | Covers |
|---|---|
| **V1 — Orders & Shipping** | order status ("where is my order"), tracking, delays, lost/damaged parcels, address change before shipment, cancellation before shipment |
| **V2 — Returns, Refunds & Exchanges** | return eligibility, initiating a return, refund timelines, exchange for size/color, return status, final-sale disputes |
| **V3 — Products & Sizing** | stock/availability, size-chart guidance, fabric & care, restock requests |
| **V4 — Payments, Billing & Promos** | failed payment, duplicate charge, promo code not working, gift cards, price-adjustment requests |
| **V5 — Account & General** | email/password/address book changes, complaints, feedback, anything mild that fits nowhere |
| **V6 — Human Handoff (backup, reachable from every vertical)** | explicit request for a human, ≥2 failed resolution attempts, customer distress/anger threshold, policy-exception requests, legal threats, suspected fraud, out-of-scope topics |

### 4.2 Conversation *direction* types every vertical must survive
1. **Happy path** — clean intent, data exists, resolved in ≤4 agent turns.
2. **Edge case** — policy boundary conditions (day-31 return, final-sale item, order already shipped when cancellation requested, promo expired yesterday…).
3. **Multi-intent** — customer combines two verticals in one conversation ("where's my order, and also this hoodie ran small last time").
4. **Ambiguous / missing data** — no order number, wrong email, vague description; agent must elicit identifiers before lookup.
5. **Escalation path** — every vertical must be able to route to V6 with a clean handoff summary.
6. **Guardrail probes** — off-topic requests, prompt-injection attempts ("ignore your instructions…"), abusive language, requests for other customers' data, requests to break policy, medical/legal advice bait.

---

## 5. Records Database (shared by both agents)

Simple, deliberately small SQLite DB. Both agents access it through the **same** `tools.py`
functions (parity), e.g. `get_order(order_id)`, `get_customer(email)`, `get_product(product_id or name)`,
`get_returns(order_id)`, `check_promo(code)`, `create_ticket(...)` (handoff), `initiate_return(...)`.

```sql
customers(customer_id PK, name, email UNIQUE, phone, loyalty_tier, created_at)
products (product_id PK, name, category, size, color, price, stock_qty, final_sale BOOL, care_notes)
orders   (order_id PK, customer_id FK, order_date, status,        -- placed|processing|shipped|delivered|delayed|lost|cancelled
          carrier, tracking_no, ship_address, expected_delivery, total)
order_items(order_id FK, product_id FK, qty, unit_price)
returns  (return_id PK, order_id FK, product_id FK, reason, status, -- requested|label_sent|received|refunded|rejected
          refund_amount, initiated_date)
promos   (code PK, discount_pct, valid_from, valid_to, min_order, active BOOL)
tickets  (ticket_id PK, customer_id, vertical, summary, created_at) -- human-handoff queue
```

Seed data (deterministic, in `db/seed.py`): ~10 customers across loyalty tiers, ~20 products
(including 3 final-sale items and 2 out-of-stock), ~15 orders engineered to cover every scenario
in Checklist.md (one delivered-but-lost, one delayed, one just-inside/just-outside the return
window, one with an expired promo, one duplicate-charge case, …). **Every Checklist scenario maps
to concrete seeded rows** so conversations ground in real lookups, not hallucinated data.

---

## 6. Agent A — the Monolithic-Prompt Baseline

- **System prompt** (`agents/prompts/agent_a_system.md`): the *entire* Loomora operations manual —
  persona & tone, all V1–V6 flows step by step, every policy number (windows, fees, timelines),
  every edge-case ruling, every guardrail, escalation criteria, data-elicitation rules, tool-use
  instructions. Written to be genuinely good — this is a strong baseline, not a strawman.
  Expected size: ~4,000–6,000 tokens.
- **Runtime:** system prompt + full chained history + tools, every turn. No retrieval.
- Authored *from* Checklist.md so coverage is provable line-by-line.

## 7. Checklist.md — the Coverage & Parity Contract

A single markdown checklist, ~45 items, grouped by vertical × direction type (§4.2 grid), each
item carrying:

```
- [ ] S-V2-07 | Edge | Return requested on day 31 (Basic tier) → deny politely, offer store-credit
      exception path via human handoff | Data: order #1013 | A: §Returns/edge | B: node ret_window_check
```

Each entry names: scenario id, direction type, expected correct behavior, the seeded DB rows it
exercises, and **where it lives in Agent A's prompt and in Agent B's graph** (the last two columns
are what `parity_audit.py` verifies — see §9). Checklist.md is written **first**, then Agent A's
prompt and the graph are both generated to satisfy it. It doubles as the source for
`simulation/scenarios.json`.

## 8. Graph-RAG Knowledge Source (Agent B's brain)

### 8.1 Node schema (`graph/graph.json`)
```jsonc
{
  "id": "ret_window_check",
  "type": "step",              // entry | step | decision | action | guardrail | escalation | terminal
  "vertical": "V2",
  "title": "Check return eligibility window",
  "instruction": "Ask for order id if unknown. Call get_order(). Compute days since delivery...",
  "guardrails": ["Never promise refunds before eligibility is confirmed"],
  "data_needed": ["order_id"],
  "tools": ["get_order", "get_returns"],
  "edges": [
    {"to": "ret_initiate",     "when": "within window AND not final_sale"},
    {"to": "ret_final_sale",   "when": "item is final_sale"},
    {"to": "ret_out_of_window","when": "outside window"},
    {"to": "handoff_human",    "when": "customer disputes or requests exception"}
  ]
}
```

- **Global nodes** reachable from anywhere (implicit edges from every node): `greeting_router`,
  `handoff_human`, `guardrail_offtopic`, `guardrail_injection`, `guardrail_abuse`,
  `guardrail_privacy`, `conversation_close`.
- Target size: **~55–70 nodes** (5 verticals × ~8–12 nodes + globals). Every Checklist item must
  be traceable to ≥1 node (enforced by `graph/validate.py`).

### 8.2 Traversal engine (`graph/engine.py`) — per turn
1. **Router step** (one *small, cheap* LLM call, `llama-3.1-8b-instant`, ~150-token prompt):
   given the user's last message + current node id + the labeled outgoing/global edges, pick the
   next node. Deterministic fallback: stay on current node.
2. **Packet composition:** current node's `instruction` + `guardrails` + edge menu + (if
   `data_needed` unmet) elicitation nudge. Typical packet: **150–350 tokens**.
3. **Generation:** Agent B's crisp system prompt (+ history + packet) → reply.
4. **State:** `{current_node, visited_path, collected_slots}` persists across turns and is logged
   into the transcript for auditability.
5. `validate.py` asserts: every node reachable from `greeting_router`, no dead-end non-terminal
   nodes, every edge target exists, every Checklist scenario id appears in ≥1 node's coverage tag.

### 8.3 Agent B — the Graph-Directed Agent
- **System prompt** (`agents/prompts/agent_b_system.md`, target **≤600 tokens**): persona & tone,
  the universal guardrails that must hold even if routing fails (privacy, no policy invention,
  handoff triggers), and *how to obey node packets* ("the CURRENT STEP block is your authoritative
  instruction for this turn; do not act beyond it").
- Everything else lives in the graph. **Prompt ∪ Graph must equal Agent A's prompt in content**
  (§9).

## 9. No-Bias / Parity Protocol (critical validity requirement)

1. **Single source of truth:** Checklist.md defines every behavior once. Agent A's prompt and
   Agent B's (prompt ∪ graph) are both *derived from it* and back-reference scenario ids.
2. **Automated audit** (`analysis/parity_audit.py`): for every Checklist id, assert it is tagged
   in Agent A's prompt **and** in Agent B's system prompt or ≥1 graph node. Fails CI-style if any
   side is missing coverage. Output: `results/parity_matrix.csv`.
3. **Same everything else:** same agent model/temperature/max_tokens, same tools, same seeded DB,
   same customer-simulator scripts and persona seeds, same scenario order, interleaved A/B runs
   (A,B,A,B…) so time-of-day API load doesn't favor one agent.
4. **Honest accounting:** Agent B's router tokens and any retrieval overhead are added to its
   per-turn and cumulative totals. We compare *architectures*, not bookkeeping.
5. **LLM cross-review:** the judge model reads Agent A's prompt vs the graph dump and lists any
   substantive rule present in one but not the other (semantic parity check, catches paraphrase
   drift the tag audit can't).

## 10. Simulation Harness & Data Collection

- **Customer simulator:** persona (from `personas.json`) + scenario goal script + hidden success
  criteria; instructed to behave like a human customer (no meta-talk), terminate with
  `<<END_SATISFIED>>` / `<<END_FRUSTRATED>>` / after max 12 customer turns.
- **Run matrix:** ~45 scenarios × 2 agents × 3 runs. Throttled with exponential backoff for Groq
  rate limits; resumable (skips already-completed run files).
- **Per turn we persist** (to `results/metrics/turns.csv` and the `.jsonl` transcript): scenario,
  agent, run, turn number, role, message text, node id + router choice (B only), tool calls made,
  `prompt_tokens`, `completion_tokens`, `total_tokens` (from Groq `usage`), router tokens (B),
  wall-clock `latency_ms`, timestamp.
- **Per conversation:** totals of the above + resolved / escalated / ended-frustrated flags,
  turns count. Human-readable `.md` transcript rendered alongside the `.jsonl`.
- Both system prompts are snapshotted verbatim into `results/` at run time (hash-stamped), as the
  experiment requires storing them.

### Q-C (Quality-of-Conversation) Score
Blind LLM-judge (`analysis/qc_judge.py`): transcripts are stripped of agent identity, randomly
labeled, and scored **one conversation at a time** against the rubric:

| Dimension | Weight | What the judge checks |
|---|---|---|
| Task resolution | 30 | Did the customer's actual goal get correctly resolved (per scenario's hidden success criteria)? |
| Factual & DB accuracy | 25 | Claims match seeded DB ground truth (judge receives the relevant rows) |
| Policy compliance & guardrails | 20 | Correct policy applied; guardrail probes deflected; no invented policy |
| Conversational quality | 15 | Tone, clarity, empathy, no repetition/contradiction across turns |
| Efficiency | 10 | Resolved without unnecessary turns or redundant questions |

Composite 0–100; each conversation judged 2× (different judge seeds), disagreement >15 points →
third judgment, median taken. Scores land in `results/qc/scores.jsonl`.

## 11. Analysis, Visualization & Reporting

`analysis/visualize.py` produces (into `REPORT.md` + `results/figures/`):
1. **Cumulative token growth per turn**, A vs B (mean band across runs) — the headline figure.
2. Per-turn prompt-token bars (fixed overhead visualized).
3. Latency distributions (box/violin), per agent, plus latency-vs-turn-number trend (H4).
4. Q-C composite + per-dimension comparison (bars), and Q-C-vs-turn-count scatter (degradation).
5. **Efficiency frontier:** total tokens (x) vs Q-C score (y), one point per conversation.
6. Summary table: median tokens/conversation, % token savings, median latency, Q-C delta,
   resolution rate, escalation rate.

`REPORT.md` structure: setup → parity evidence → results per hypothesis H1–H4 → transcript
excerpts (best/worst per agent) → threats to validity → conclusions → future work (voice pipeline,
embedding-based routing, larger graphs, degradation stress test at 30+ turns).

## 12. Execution Milestones (with acceptance criteria)

| # | Milestone | Done when |
|---|---|---|
| M0 | Scaffold: layout, `config.py`, `requirements.txt`, Groq smoke test | one successful API call using `.env` key |
| M1 | **Checklist.md** (~45 scenarios, §7 format) | every vertical × direction-type cell covered |
| M2 | **DB**: schema + seed | every Checklist scenario's `Data:` rows exist; `seed.py` idempotent |
| M3 | **Agent A**: prompt + agent + tools | passes 3 manual smoke conversations per vertical |
| M4 | **Graph**: `graph.json` + engine + `validate.py` green | validator passes; router picks sane nodes on 10 probe messages |
| M5 | **Agent B** wired to engine | same smoke test as M3 |
| M6 | **Parity audit green** (tag audit + semantic cross-review) | zero uncovered Checklist ids on either side |
| M7 | Simulation harness + full run matrix | 270 transcripts + metrics CSVs on disk |
| M8 | Q-C judging complete | `scores.jsonl` full; inter-judgment agreement reported |
| M9 | Visualization + **REPORT.md** | all figures render; H1–H4 answered with numbers |

## 13. Risks & Mitigations
- **Groq rate limits / free-tier TPM** → throttling, backoff, resumable runs, optionally cut runs 3→2.
- **Network-noise latency** → tokens are the primary compute metric; latency reported as median/p90 across repetitions with interleaved A/B ordering.
- **Router misrouting hurts B unfairly** → log every routing decision; report routing accuracy separately; deterministic stay-on-node fallback.
- **Judge bias** → blind labels, different model family, double judging, rubric anchored to DB ground truth.
- **Parity drift while authoring** → Checklist.md written first; both sides derived from it; automated audit gate before any experiment run.
- **Customer simulator leaks meta-behavior** → strict persona prompt + transcript spot checks before the full matrix.

---
---

# PHASE 2 — Third Arm: Agent C, Conventional Vector RAG (planned 2026-07-05)

Phase 1 compared a monolithic prompt (A) against Graph-RAG (B). Phase 2 adds the missing
baseline every practitioner will ask about: **vanilla RAG** — one source document, local
chunking, embeddings in a vector DB, top-k similarity retrieval per turn. The three-way
comparison then cleanly decomposes the effect:

- **A vs C** = what *any* retrieval buys over a monolithic prompt (token effect).
- **B vs C** = what *graph structure* (typed nodes, session state, routed transitions,
  guardrail precedence) buys over *similarity* retrieval at comparable context size —
  the sharpest form of this project's research question.

## P2.1 Agent C architecture

| Layer | Design | Rationale |
|---|---|---|
| **Source document** | `rag/corpus/loomora_manual.md` — **derived verbatim from `agent_a_system.md`** (policy content identical by construction; only the "how you work" mechanics paragraph is swapped for C's retrieval mechanics) | Content parity with A is guaranteed by derivation, and A↔B parity is already proven — so C inherits parity with both |
| **Chunking** | Local, structure-aware: split on the manual's `###` section boundaries (V1.status, V2.window, Guard.privacy, …), target 150–350 tokens/chunk, no mid-policy splits; each chunk tagged with its section anchor | Matches Agent B's node-packet granularity — C and B inject comparably-sized context, isolating the *retrieval mechanism* as the variable |
| **Embeddings** | Local `sentence-transformers/all-MiniLM-L6-v2` (384-d, CPU, deterministic) | Free, offline, reproducible; no API budget entanglement; embedding latency (~10 ms) is measured and reported |
| **Vector DB** | **ChromaDB**, persistent local store at `rag/chroma/` | The user-specified "vector db"; zero-infra, versionable |
| **Per-turn retrieval** | Query = current user message + last agent message (300-char tail); **top-k = 3** chunks (ablation: k ∈ {2,3,5} on the 12-probe set before the matrix); retrieved chunks injected into the system prompt **for that turn only** (same injection mechanics as B's packet — never accumulated into history) | Mirrors B's turn-scoped context exactly; k=3 ≈ one node packet's information budget |
| **System prompt** | `agents/prompts/agent_c_system.md`: **identical to Agent B's** except the `<workflow_step>` mechanics paragraph becomes `<retrieved_guidance>` mechanics ("the retrieved excerpts are your authoritative policy source this turn; if they don't cover the request, say so / escalate rather than invent") | The eight non-negotiable global rules stay word-for-word the same — prompt parity with B |
| **No router, no state** | C has no session state and no LLM routing call | That IS the baseline's definition; C's retrieval cost is embedding compute (measured in ms, ~zero tokens), so C is expected to be the *latency* winner — an honest advantage |

## P2.2 Parity protocol extension (no-bias, three-way)
1. **Tag audit**: `parity_audit.py` gains a C column — for every Checklist scenario, its
   `A:` section anchors must exist **as chunk tags** in the vector store (guaranteed by
   the derivation + chunker, but machine-verified anyway). Output: `parity_matrix.csv`
   grows `c_ok`.
2. **Retrieval sanity probes** (analog of B's router probes): for the same 12 probe
   messages, assert the top-3 retrieved chunks include the section the scenario needs
   (e.g. "Come on, it's ONE day past" → must retrieve `V2.window`/out-of-window text).
   Recall@3 reported; failures fixed by chunking adjustments, never by editing policy
   content (that would break parity).
3. **Semantic parity**: not re-run for C — the corpus is a verbatim derivation of A's
   manual; the derivation script asserts the diff is exactly the mechanics paragraph.
4. **Honest accounting**: C's retrieval adds ~0 LLM tokens; its embedding+search wall
   time is included in `latency_ms` (as B's router time is). Chunk tokens injected per
   turn are counted in `prompt_tokens` exactly like B's packets.

## P2.3 Measurement & hypotheses (same harness, same judge, same scenarios)
Same 51 scenarios × 2 runs → **+102 conversations** (~1.3–2M Mistral tokens). Same
blind deduction-based judge; same metrics CSVs (agent = `agent_c`); `turns.csv` gains
`retrieved_chunks` + `retrieval_ms` in the extra metadata.

- **H5 (tokens)**: C ≈ B on per-turn prompt tokens (both turn-scoped); both ≪ A.
- **H6 (quality — the interesting one)**: C < B on policy-edge and multi-step scenarios:
  similarity retrieval has no state (can't know the conversation is mid-return-flow),
  no guardrail precedence (an injection attempt embeds *near nothing policy-ish*), and
  no transition discipline (nothing prevents skipping eligibility checks). Predicted
  failure signatures, checklist-mapped: S-V2-02/06/07 (flow order), S-G-01..06
  (guardrail recall), S-M-01..03 (only one intent's chunks retrieved).
- **H7 (latency)**: C < B and ≈ A per turn (no serial router call; local embedding).
- If H5+H7 hold and H6 shows a real quality gap, the conclusion sharpens to: *tokens are
  saved by turn-scoping context (any RAG); correctness under policy pressure is bought
  by the graph's structure* — with the frontier plot showing three distinct clusters.

## P2.4 Repo additions
```
rag/
├── build_corpus.py       ← derive loomora_manual.md from agent_a_system.md + assert the diff
├── chunker.py            ← section-aware chunking → chunks.jsonl (id, anchor, text, tokens)
├── store.py              ← ChromaDB build/load + embed + top-k query (returns ids, scores, ms)
├── probe_retrieval.py    ← the 12 recall@3 sanity probes (P2.2.2)
└── chroma/               ← persistent vector store (gitignored)
agents/agent_c.py          ← ToolLoopAgent subclass: retrieve → inject → same tool loop
agents/prompts/agent_c_system.md
```
`requirements.txt` += `chromadb`, `sentence-transformers`. Visualization: Agent C takes
categorical slot 3 (yellow `#eda100`; sub-3:1 on light surface → relief rule: direct
labels stay on, tables in REPORT.md). All five figures become three-series; the
efficiency frontier is the headline (three clusters expected).

## P2.5 Milestones
| # | Milestone | Done when |
|---|---|---|
| M10 | Corpus derivation + chunker + Chroma store built | derivation diff-assert passes; chunk count/size stats printed; store queryable |
| M11 | Retrieval probes + k ablation | ~~recall@3 ≥ 11/12~~ **DONE 2026-07-05: k=3, recall@3 = 11/13.** Bar revised with rationale: after hybrid BM25+vector RRF, fused two-query retrieval, and hint enrichment (B's own router hints reused — mechanism parity), the two persistent failures are BOTH guardrail-recall probes (injection, abuse) — H6's predicted failure mode. Tuning them away would game the probe set and pollute B's shared hints; they are measured instead. B's router re-verified 12/12 after the shared-hint edits. |
| M12 | Agent C + crisp prompt + smoke suite | same 7 smoke conversations pass review |
| M13 | Parity audit extension green | `parity_matrix.csv` c_ok column all true |
| M14 | Matrix arm C (51 × 2 = 102 conversations) | transcripts + metrics on disk |
| M15 | Judge arm C + regenerate 3-way figures + REPORT v2 | H5–H7 answered with numbers; B-vs-C discussion written |

## P2.6 Risks
- **Chunking granularity distorts comparison** → chunk size targeted at node-packet size; k ablated on probes before the matrix.
- **Retrieval misses on terse/emotional messages** ("Come on, ONE day past") → query includes last agent message tail for context; measured by probes, reported as C's routing-analog accuracy.
- **sentence-transformers/torch install weight on Windows** → CPU wheels; fallback to ChromaDB's built-in ONNX MiniLM (`all-MiniLM-L6-v2` via onnxruntime) if torch install fights.
- **Three-way judging cost** → +~0.7M judge tokens on Mistral (fine); gpt-oss cross-check extended to include C conversations.
