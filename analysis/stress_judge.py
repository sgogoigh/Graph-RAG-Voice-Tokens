"""H4 stress test: per-goal judge for marathon conversations.

Unlike qc_judge (one score per conversation), this scores EACH numbered goal in the
marathon separately — giving resolution quality as a function of goal POSITION, which
is the degradation signal H4 needs: does issue #7 get handled worse than issue #1,
and does that slope differ by architecture?

Judged twice (temp 0.0 / 0.6): per-goal score = mean, resolved = strict AND of the two
judgments (conservative). Rows appended to results/stress/qc/goal_scores.jsonl,
one per (scenario, agent, run, goal). Resumable per conversation.

Run:  .venv/Scripts/python analysis/stress_judge.py
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

STRESS_ROOT = config.RESULTS_DIR / "stress"
SCORES = STRESS_ROOT / "qc" / "goal_scores.jsonl"

JUDGE_PROMPT = """\
You are a strict, impartial quality auditor for customer-support conversations at \
Loomora, an online clothing store. This customer worked through a NUMBERED LIST of \
issues in one long conversation. Judge how the SUPPORT AGENT handled EACH issue.

THE CUSTOMER'S ISSUE LIST (in order): {goal}

CORRECT EXPECTED OUTCOME PER ISSUE (ground truth): {success}

DATA THE AGENT'S TOOLS RETURNED (authoritative ground truth):
{tool_evidence}

CONVERSATION:
{dialogue}

For EACH numbered issue, decide: was it correctly resolved per its expected outcome \
(resolved true/false), and score its handling 0-100 by deduction (start 100; -30 wrong \
or missing resolution; -30 per claim contradicting tool data; -25 policy misapplied or \
unauthorized action; -15 customer had to repeat or push; -10 each for redundant \
questions, jargon, or tone misses). An issue the agent never addressed at all scores 0 \
and resolved=false.

Reply with STRICT JSON only:
{{"goals": [{{"n": 1, "resolved": true, "score": 85, "note": "<one sentence>"}}, ...]}} \
with one entry per numbered issue, in order."""


def load_transcript(path: Path) -> dict | None:
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    meta = next((x for x in lines if x.get("type") == "meta"), None)
    end = next((x for x in lines if x.get("type") == "end"), None)
    turns = [x for x in lines if x.get("type") == "turn"]
    return {"meta": meta, "end": end, "turns": turns} if (meta and end and turns) else None


def n_goals(goal_text: str) -> int:
    # list markers like "7)" only — not "34)" in "between 32 and 34)" or "O1002)"
    return max(int(m) for m in re.findall(r"(?<![0-9A-Za-z])([1-9])\)", goal_text))


def build_prompt(t: dict) -> str:
    dialogue, evidence = [], []
    for turn in t["turns"]:
        dialogue.append(f"Customer: {turn['customer_msg']}")
        dialogue.append(f"Agent: {turn['agent_msg']}")
        for tc in turn.get("tool_call_details", []):
            evidence.append(f"- {tc['name']}({tc['arguments']}) -> {tc['result'][:300]}")
    return JUDGE_PROMPT.format(
        goal=t["meta"]["goal"], success=t["meta"]["success_criteria"],
        tool_evidence="\n".join(evidence) or "(no tools called)",
        dialogue="\n".join(dialogue),
    )


def judge_once(prompt: str, expect_n: int, temperature: float) -> list[dict] | None:
    r = chat(config.JUDGE_MODEL, [{"role": "user", "content": prompt}],
             temperature=temperature, max_tokens=3000, purpose="judge")
    m = re.search(r"\{.*\}", r.message.content or "", re.S)
    if not m:
        return None
    try:
        goals = json.loads(m.group(0))["goals"]
        by_n = {int(g["n"]): g for g in goals}
        return [{"n": n, "resolved": bool(by_n[n]["resolved"]),
                 "score": max(0, min(100, int(by_n[n]["score"]))),
                 "note": str(by_n[n].get("note", ""))[:300]}
                for n in range(1, expect_n + 1)]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def main() -> int:
    done: set[tuple] = set()
    if SCORES.exists():
        for line in SCORES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["scenario"], r["agent"], r["run"]))

    paths = sorted((STRESS_ROOT / "transcripts").glob("agent_*/ST-*_run*.jsonl"))
    SCORES.parent.mkdir(parents=True, exist_ok=True)
    judged = skipped = 0

    with SCORES.open("a", encoding="utf-8") as out:
        for p in paths:
            t = load_transcript(p)
            if t is None:
                continue
            key = (t["meta"]["scenario"], t["meta"]["agent"], t["meta"]["run"])
            if key in done:
                skipped += 1
                continue
            expect = n_goals(t["meta"]["goal"])
            prompt = build_prompt(t)
            j1 = judge_once(prompt, expect, 0.0)
            j2 = judge_once(prompt, expect, 0.6)
            judgments = [j for j in (j1, j2) if j]
            if not judgments:
                print(f"WARN unparseable: {p.name}")
                continue
            for n in range(1, expect + 1):
                entries = [j[n - 1] for j in judgments]
                row = {
                    "scenario": key[0], "agent": key[1], "run": key[2], "goal": n,
                    "resolved": all(e["resolved"] for e in entries),
                    "score": round(sum(e["score"] for e in entries) / len(entries), 1),
                    "n_judgments": len(entries),
                    "notes": [e["note"] for e in entries],
                    "turns": t["end"]["turns"], "total_tokens": t["end"]["total_tokens"],
                }
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            judged += 1
            resolved = sum(all(j[n - 1]["resolved"] for j in judgments) for n in range(1, expect + 1))
            print(f"[{judged}] {key[0]} {key[1]} run{key[2]}: {resolved}/{expect} goals resolved")

    print(f"\nJudged {judged} conversations, skipped {skipped}. -> {SCORES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
