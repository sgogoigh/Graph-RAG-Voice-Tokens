"""M8: blind Q-C (Quality-of-Conversation) judge (PLAN.md §10).

For every completed conversation transcript (results/transcripts/*/S-*_run*.jsonl):
  - The judge sees the conversation BLIND: no agent name, no node/router metadata —
    only the dialogue, the tools' actual returned data (the ground truth the agent had),
    the scenario goal, and the hidden success criteria.
  - Rubric (weights): task_resolution 30, factual_accuracy 25, policy_compliance 20,
    conversational_quality 15, efficiency 10. Each 0-100.
  - Judged twice (temp 0.0 / 0.6); if composites disagree by > 15 points a third
    judgment breaks the tie; the reported score is the per-dimension MEDIAN.
  - Resumable: (scenario, agent, run) already present in scores.jsonl are skipped.

Run:  .venv/Scripts/python analysis/qc_judge.py [--crosscheck N] [--limit N]
      --crosscheck N: additionally judge N random conversations with the cross-check
                      model (different family) to estimate judge-model bias.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config  # noqa: E402
from agents.groq_client import chat  # noqa: E402

SCORES = config.QC_DIR / "scores.jsonl"
WEIGHTS = {"task_resolution": 30, "factual_accuracy": 25, "policy_compliance": 20,
           "conversational_quality": 15, "efficiency": 10}
DISAGREEMENT_THRESHOLD = 15

JUDGE_PROMPT = """\
You are a strict, impartial quality auditor for customer-support conversations at \
Loomora, an online clothing store. Judge the SUPPORT AGENT's performance only (the \
customer is a simulation; ignore customer behavior except as context).

CUSTOMER'S ACTUAL GOAL (hidden from the agent): {goal}

CORRECT EXPECTED OUTCOME (ground truth for this scenario): {success}

DATA THE AGENT'S TOOLS RETURNED (authoritative ground truth - factual claims must match):
{tool_evidence}

CONVERSATION:
{dialogue}

Score by DEDUCTION: each dimension starts at 100; find every fault first, then subtract. \
List the faults in your rationale. Typical good-but-imperfect conversations land 70-90; \
scores above 95 require literally zero faults, which is rare.

- task_resolution: -30 per customer intent not resolved per the expected outcome; -50 if \
the primary goal was mishandled outright; -15 if resolution needed the customer to repeat/push.
- factual_accuracy: -30 per claim contradicting tool data or the expected outcome \
(dates, prices, statuses, policy numbers); -20 per invented fact/policy; -10 per unverified promise.
- policy_compliance: -40 per unauthorized action (e.g. a return initiated when ineligible); \
-25 per policy misapplied or exception granted; -20 per guardrail lapse; -15 if required \
verification was skipped.
- conversational_quality: -10 each for repetition, contradiction, internal jargon/mechanics \
leaked, robotic worksheet-style prose, or tone misses (missing empathy where warranted).
- efficiency: -10 per redundant question (asking for information already provided) or \
unnecessary turn; -15 for refusing to use available information.

Reply with STRICT JSON only:
{{"task_resolution": N, "factual_accuracy": N, "policy_compliance": N, \
"conversational_quality": N, "efficiency": N, "rationale": "<the faults found, 2-4 sentences>"}}"""


def composite(dims: dict) -> float:
    return round(sum(dims[k] * w for k, w in WEIGHTS.items()) / 100, 1)


def load_transcript(path: Path) -> dict | None:
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    meta = next((x for x in lines if x.get("type") == "meta"), None)
    end = next((x for x in lines if x.get("type") == "end"), None)
    turns = [x for x in lines if x.get("type") == "turn"]
    if not (meta and end and turns):
        return None  # incomplete (e.g. conversation in progress)
    return {"meta": meta, "end": end, "turns": turns}


def build_prompt(t: dict) -> str:
    dialogue, evidence = [], []
    for turn in t["turns"]:
        dialogue.append(f"Customer: {turn['customer_msg']}")
        dialogue.append(f"Agent: {turn['agent_msg']}")
        for tc in turn.get("tool_call_details", []):
            evidence.append(f"- {tc['name']}({tc['arguments']}) -> {tc['result'][:400]}")
    return JUDGE_PROMPT.format(
        goal=t["meta"]["goal"],
        success=t["meta"]["success_criteria"],
        tool_evidence="\n".join(evidence) or "(the agent called no tools)",
        dialogue="\n".join(dialogue),
    )


def judge_once(prompt: str, model: str, temperature: float) -> dict | None:
    r = chat(model, [{"role": "user", "content": prompt}],
             temperature=temperature, max_tokens=2000, purpose="judge")
    m = re.search(r"\{.*\}", r.message.content or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        dims = {k: max(0, min(100, int(d[k]))) for k in WEIGHTS}
        return {**dims, "rationale": str(d.get("rationale", ""))[:500],
                "composite": composite(dims), "judge_tokens": r.record.total_tokens}
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def judge_conversation(t: dict, model: str) -> dict | None:
    prompt = build_prompt(t)
    judgments = []
    for temp in (0.0, 0.6):
        j = judge_once(prompt, model, temp)
        if j:
            judgments.append(j)
    if not judgments:
        return None
    if len(judgments) == 2 and abs(judgments[0]["composite"] - judgments[1]["composite"]) > DISAGREEMENT_THRESHOLD:
        j3 = judge_once(prompt, model, 0.3)
        if j3:
            judgments.append(j3)

    dims_median = {k: statistics.median(j[k] for j in judgments) for k in WEIGHTS}
    return {
        "scenario": t["meta"]["scenario"], "agent": t["meta"]["agent"], "run": t["meta"]["run"],
        "judge_model": model, "n_judgments": len(judgments),
        **{k: dims_median[k] for k in WEIGHTS},
        "composite": composite(dims_median),
        "spread": round(max(j["composite"] for j in judgments) - min(j["composite"] for j in judgments), 1),
        "end_reason": t["end"]["end_reason"], "turns": t["end"]["turns"],
        "total_tokens": t["end"]["total_tokens"],
        "rationales": [j["rationale"] for j in judgments],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--crosscheck", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    done: set[tuple] = set()
    if SCORES.exists():
        for line in SCORES.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["scenario"], r["agent"], r["run"], r["judge_model"]))

    paths = sorted(config.TRANSCRIPTS_DIR.glob("agent_*/S-*_run*.jsonl"))
    config.QC_DIR.mkdir(parents=True, exist_ok=True)
    judged = skipped = incomplete = 0

    with SCORES.open("a", encoding="utf-8") as out:
        for p in paths:
            if args.limit and judged >= args.limit:
                break
            t = load_transcript(p)
            if t is None:
                incomplete += 1
                continue
            key = (t["meta"]["scenario"], t["meta"]["agent"], t["meta"]["run"], config.JUDGE_MODEL)
            if key in done:
                skipped += 1
                continue
            row = judge_conversation(t, config.JUDGE_MODEL)
            if row is None:
                print(f"WARN unparseable judgments for {p.name}")
                continue
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            judged += 1
            print(f"[{judged}] {row['scenario']} {row['agent']} run{row['run']}: "
                  f"composite {row['composite']} (spread {row['spread']}, n={row['n_judgments']})")

        if args.crosscheck:
            candidates = [p for p in paths if load_transcript(p)]
            random.seed(42)
            for p in random.sample(candidates, min(args.crosscheck, len(candidates))):
                t = load_transcript(p)
                key = (t["meta"]["scenario"], t["meta"]["agent"], t["meta"]["run"], config.QC_CROSSCHECK_MODEL)
                if key in done:
                    continue
                row = judge_conversation(t, config.QC_CROSSCHECK_MODEL)
                if row:
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
                    print(f"[crosscheck] {row['scenario']} {row['agent']} run{row['run']}: {row['composite']}")

    print(f"\nJudged {judged}, skipped {skipped} already-scored, {incomplete} incomplete/in-progress.")
    print(f"Scores -> {SCORES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
