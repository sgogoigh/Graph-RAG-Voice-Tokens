"""M6 semantic parity cross-review (PLAN.md §9.5) — LLM-checked content parity.

The tag audit proves every scenario is MAPPED on both sides; this pass checks the mapped
CONTENT actually agrees: the judge model diffs each section of Agent A's manual against
Agent B's system prompt + the graph nodes for the same area, and reports substantive
rules present on one side but missing from the other.

Chunked per section because judge TPM (8k) can't hold both corpora at once.
Findings go to results/semantic_parity.json for human triage — some findings are false
positives (the judge can't see every node the router might surface).

Run:  .venv/Scripts/python analysis/semantic_parity.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config  # noqa: E402
from agents.groq_client import chat  # noqa: E402

# manual h1 section -> graph verticals whose nodes are Agent B's counterpart material
SECTION_MAP = [
    ("core rules & identity & tools", r"^# Loomora", ["core", "V1-elicit"]),
    ("V1 Orders & Shipping",          r"^# V1 ",     ["V1"]),
    ("V2 Returns & Refunds",          r"^# V2 ",     ["V2"]),
    ("V3 Products & Sizing",          r"^# V3 ",     ["V3"]),
    ("V4 Payments & Promos",          r"^# V4 ",     ["V4"]),
    ("V5 Account & General",          r"^# V5 ",     ["V5"]),
    ("V6 Human Handoff",              r"^# V6 ",     ["V6", "G-legal", "V2-oow"]),
    ("Hard Guardrails",               r"^# Hard ",   ["G"]),
]

JUDGE_PROMPT = """\
You are auditing two customer-support agent configurations for INSTRUCTION PARITY. They \
must operate under identical policy. Agent A has one monolithic manual; Agent B has a \
short global system prompt plus per-step workflow instructions that a router surfaces \
when relevant.

AGENT A MANUAL SECTION ({name}):
<<<
{a_section}
>>>

AGENT B GLOBAL SYSTEM PROMPT (applies on every turn):
<<<
{b_prompt}
>>>

AGENT B WORKFLOW STEPS for this area:
<<<
{b_nodes}
>>>

List SUBSTANTIVE policy/behavior differences only: rules, numbers, thresholds, \
conditions, or required actions present on one side and absent from the other. Ignore \
style, ordering, wording, and tool/router mechanics.

IMPORTANT — this is ONE section of Agent A's manual; A's other sections (global rules, \
guardrails) are not shown. So compare asymmetrically:
- missing_in_b: rules in THIS Agent A section that appear NOWHERE in B's system prompt \
or steps shown.
- missing_in_a: area-specific policy in B's WORKFLOW STEPS absent from this A section. \
Do NOT report items from B's global system prompt here — A has global sections for those.

Reply with strict JSON only: {{"missing_in_b": ["short description", ...], \
"missing_in_a": ["short description", ...]}}. Use empty lists if parity holds."""


def split_manual(text: str) -> list[tuple[str, str]]:
    """Split agent_a_system.md into (first_line, body) h1 sections."""
    parts = re.split(r"(?=^# )", text, flags=re.M)
    return [(p.splitlines()[0], p) for p in parts if p.strip()]


def nodes_for(graph: dict, keys: list[str]) -> str:
    sel = []
    for n in graph["nodes"]:
        v = n["vertical"]
        take = (
            v in keys
            or ("V1-elicit" in keys and n["id"] == "elicit_order")
            or ("G-legal" in keys and n["id"] == "guardrail_legal")
            or ("V2-oow" in keys and n["id"] == "ret_out_of_window")
        )
        if take:
            g = ("\n  guardrails: " + "; ".join(n["guardrails"])) if n["guardrails"] else ""
            sel.append(f"[{n['id']}] {n['title']}\n  {n['instruction']}{g}")
    return "\n\n".join(sel)


def main() -> int:
    manual = (config.PROMPTS_DIR / "agent_a_system.md").read_text(encoding="utf-8")
    b_prompt = (config.PROMPTS_DIR / "agent_b_system.md").read_text(encoding="utf-8")
    graph = json.loads(config.GRAPH_PATH.read_text(encoding="utf-8"))
    sections = split_manual(manual)

    results, total_findings = [], 0
    for name, head_re, vert_keys in SECTION_MAP:
        section = next((body for first, body in sections if re.match(head_re, first)), None)
        if section is None:
            print(f"WARN: no manual section matched {head_re}")
            continue
        prompt = JUDGE_PROMPT.format(
            name=name, a_section=section.strip(), b_prompt=b_prompt.strip(),
            b_nodes=nodes_for(graph, vert_keys),
        )
        # Pinned to the cross-check model (gpt-oss-120b): the Mistral judge fabricated
        # gaps on this careful-reading task (2026-07-05 run: 51 findings, spot-checks
        # showed the "missing" rules present verbatim). 8 calls fit Groq's daily budget.
        r = chat(config.QC_CROSSCHECK_MODEL, [{"role": "user", "content": prompt}],
                 temperature=config.JUDGE_TEMPERATURE, max_tokens=2000, purpose="judge")
        raw = (r.message.content or "").strip()
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            verdict = json.loads(m.group(0)) if m else {"parse_error": raw[:300]}
        except json.JSONDecodeError:
            verdict = {"parse_error": raw[:300]}
        n_findings = len(verdict.get("missing_in_b", [])) + len(verdict.get("missing_in_a", []))
        total_findings += n_findings
        results.append({"section": name, "verdict": verdict,
                        "judge_tokens": r.record.total_tokens})
        print(f"[{name}] findings: {n_findings}")
        for side in ("missing_in_b", "missing_in_a"):
            for item in verdict.get(side, []):
                print(f"    {side}: {item}")

    out = config.RESULTS_DIR / "semantic_parity.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{total_findings} total finding(s) -> {out}")
    print("Triage note: findings are candidates, not verdicts — fix real gaps, document dismissals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
