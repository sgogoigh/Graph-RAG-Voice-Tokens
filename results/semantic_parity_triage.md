# Semantic Parity Review — Triage Record (M6)

Date: 2026-07-05 · Judge: `openai/gpt-oss-120b`, temp 0 · Method: per-section diff of
Agent A's manual vs Agent B's system prompt + graph nodes (`analysis/semantic_parity.py`),
raw output in `semantic_parity.json`.

## Run 1 (naive prompt): 11 findings — all methodology false positives
All 11 were global rules from Agent B's system prompt flagged as "missing in A" while the
judge was shown only A's **V3 section**. Every rule exists in A's core/guardrail sections,
each of which passed its own comparison with 0 findings (identity verification → A
"Identity verification" section; privacy → A Guard.privacy; truth/no-invention, style,
one-question-at-a-time, internals, date rule → A "Core conversation rules"; payment
hygiene → A V4.duplicate/V4.failed; escalation → A V6.request). One finding ("workflow
mismatch handling") is Agent-B router mechanics with no A counterpart by construction.
The judge prompt was made direction-aware and the review re-run.

## Run 2 (direction-aware prompt): 2 findings — both dismissed
| # | Finding | Verdict | Evidence |
|---|---|---|---|
| 1 | V3: "report stock exactly as returned by the tool" missing in A | **Dismissed — present in A** | A core rules: "Never invent data. Order details, stock, prices, promo terms, and return states come only from tools." (global section, outside the V3 chunk shown) |
| 2 | Guardrails: legal-threat handling missing in A | **Dismissed — present in A** | A §V6.legal (compared in the V6 chunk, which returned 0 findings with guardrail_legal included) |

## Verdict
- Tag audit (`parity_matrix.csv`): **51/51 scenarios anchored on both sides — PASS**
- Semantic review: **0 substantive gaps after triage — PASS**

Parity gate is GREEN; the experiment matrix (M7) may run. Re-run both audits after ANY
edit to `agent_a_system.md`, `agent_b_system.md`, or `graph.json`.
