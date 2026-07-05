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

## Run 3 (2026-07-05, after agent_b_system.md packet-hygiene edit): 4 findings — all dismissed
Same false-positive class as run 2 — the rule exists in a DIFFERENT Agent A section than
the chunk compared: stock fidelity → A core Truth rule; out-of-window return handling →
A §V2.window (its own V2 comparison: 0 findings); priority for chargebacks/fraud →
A §V4.chargeback + §Guard.fraud; legal-threat handling → A §V6.legal. No policy edit was
made in this iteration (only packet-formatting mechanics), so semantic parity is
unchanged by construction.

## Run 4 (2026-07-05, after the symmetric anti-fabrication rule + Phase-2 corpus rebuild)
**Judge-model incident:** the first re-run used `config.JUDGE_MODEL` (now Mistral-small,
changed in M8 for Q-C budget reasons) and produced **51 findings — fabricated**: spot
checks showed the "missing" rules present verbatim (e.g. refund timing in `ord_cancel`,
48h rule in `ord_lost`, store-credit-free in `ret_initiate`). Semantic parity is a
careful-reading task; the script is now PINNED to the cross-check model
(`openai/gpt-oss-120b`), whose re-run produced 7 findings, all dismissed:
| Finding | Verdict |
|---|---|
| 4× "missing in A": tier windows / window math / no-initiate-outside-window / V2 ticket routing (V6 section) | Dismissed — all verbatim in A §V2.window; cross-section artifact |
| "Generic exception rule missing in B" | Dismissed — B system prompt "No exceptions… only exception path is a human-review ticket" + handoff_human |
| "Privacy → lockout path missing in B" | Dismissed — exists as graph EDGE guardrail_privacy→acct_lockout (the judge dump includes node instructions, not edges) |
| "Legal guardrail missing in A" | Dismissed — A §V6.legal (recurring artifact, see Run 2) |

The anti-fabrication sentence itself is word-identical in all three prompts (A core
rules, B Truth rule, C Truth rule) and flows into C's corpus via the asserted derivation.

## Verdict
- Tag audit (`parity_matrix.csv`): **51/51 scenarios anchored on both sides — PASS**
- Semantic review: **0 substantive gaps after triage — PASS**

Parity gate is GREEN; the experiment matrix (M7) may run. Re-run both audits after ANY
edit to `agent_a_system.md`, `agent_b_system.md`, or `graph.json`.
