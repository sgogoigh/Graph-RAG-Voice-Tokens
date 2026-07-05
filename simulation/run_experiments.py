"""M7 experiment harness: scenario x agent x run matrix (PLAN.md §10).

Design constraints honored:
- RESUMABLE: one .jsonl per conversation, written atomically at the end; existing files
  are skipped, so the matrix survives Groq daily-budget exhaustion and continues the
  next day (the client fast-fails on TPD/RPD 429s with a RuntimeError we catch here).
- FAIR: DB reseeded before every conversation; A and B get identical scenario scripts;
  which agent goes first alternates per run; router/customer costs recorded separately;
  prompt + graph snapshots are hash-stamped at session start.
- METRICS: one row per agent turn in turns.csv, one row per conversation in
  conversations.csv (append-mode, header on create).

Run:  .venv/Scripts/python simulation/run_experiments.py [--limit N] [--runs N]
                                                          [--agents a,b] [--scenarios id,id]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config  # noqa: E402
from agents.agent_a import AgentA  # noqa: E402
from agents.agent_b import AgentB  # noqa: E402
from agents.agent_c import AgentC  # noqa: E402
from agents.base import render_transcript_md  # noqa: E402
from db import seed as dbseed  # noqa: E402
from graph.engine import Graph  # noqa: E402
from rag.store import RagStore  # noqa: E402
from simulation.customer import CustomerSim, end_reason  # noqa: E402

# Output locations — mutable so side experiments (e.g. the H4 stress test) can run the
# same harness into their own namespace via --out-root without touching matrix data.
PATHS = {
    "transcripts": config.TRANSCRIPTS_DIR,
    "turns_csv": config.METRICS_DIR / "turns.csv",
    "convs_csv": config.METRICS_DIR / "conversations.csv",
    "snapshots": config.RESULTS_DIR / "prompt_snapshots",
}


def set_out_root(root: Path) -> None:
    PATHS.update(
        transcripts=root / "transcripts",
        turns_csv=root / "metrics" / "turns.csv",
        convs_csv=root / "metrics" / "conversations.csv",
        snapshots=root / "prompt_snapshots",
    )

TURN_FIELDS = ["scenario", "agent", "run", "turn", "customer_msg", "agent_msg",
               "latency_ms", "prompt_tokens", "completion_tokens", "total_tokens",
               "api_calls", "router_prompt_tokens", "router_completion_tokens",
               "customer_tokens", "tool_calls", "node", "router_fallback", "ts"]
CONV_FIELDS = ["scenario", "agent", "run", "turns", "prompt_tokens", "completion_tokens",
               "total_tokens", "router_tokens", "customer_tokens", "latency_ms_total",
               "end_reason", "escalated", "ts"]

GRAPH = Graph.load()


def snapshot_sources() -> None:
    snap = PATHS["snapshots"]
    snap.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for src in [config.PROMPTS_DIR / "agent_a_system.md",
                config.PROMPTS_DIR / "agent_b_system.md",
                config.PROMPTS_DIR / "agent_c_system.md",
                config.GRAPH_PATH,
                config.ROOT / "rag" / "chunks.jsonl"]:
        text = src.read_text(encoding="utf-8")
        (snap / src.name).write_text(text, encoding="utf-8")
        manifest[src.name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    manifest["agent_model"] = config.AGENT_MODEL
    manifest["router_model"] = config.ROUTER_MODEL
    manifest["customer_model"] = config.CUSTOMER_MODEL
    manifest["snapshotted_at"] = datetime.now().isoformat(timespec="seconds")
    (snap / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def reseed() -> None:
    conn = sqlite3.connect(config.DB_PATH)
    try:
        dbseed.seed(conn)
    finally:
        conn.close()


def append_csv(path: Path, fields: list[str], row: dict) -> None:
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)


_RAG_STORE: RagStore | None = None


def make_agent(name: str):
    if name == "agent_a":
        return AgentA()
    if name == "agent_b":
        return AgentB(GRAPH)
    global _RAG_STORE
    _RAG_STORE = _RAG_STORE or RagStore()  # load the vector store once per session
    return AgentC(_RAG_STORE)


def run_conversation(agent_name: str, scenario: dict, run_no: int) -> dict:
    """Run one full conversation; returns the conversations.csv row."""
    sid = scenario["id"]
    out_jsonl = PATHS["transcripts"] / agent_name / f"{sid}_run{run_no}.jsonl"
    out_md = out_jsonl.with_suffix(".md")

    reseed()
    agent = make_agent(agent_name)
    sim = CustomerSim(scenario)

    history: list[dict] = []
    md_turns: list[dict] = []
    jl: list[dict] = [{"type": "meta", "scenario": sid, "agent": agent_name, "run": run_no,
                       "persona": scenario["persona"], "goal": scenario["goal"],
                       "success_criteria": scenario["success_criteria"],
                       "started_at": datetime.now().isoformat(timespec="seconds")}]
    totals = {"p": 0, "c": 0, "router": 0, "customer": 0, "latency": 0.0}
    reason, escalated = "max_turns", False

    customer_msg = sim.opening()
    for turn in range(1, scenario["max_customer_turns"] + 1):
        history.append({"role": "user", "content": customer_msg})
        md_turns.append({"role": "user", "content": customer_msg})

        reply, m = agent.respond(history)
        history.append({"role": "assistant", "content": reply})
        md_turns.append({"role": "assistant", "content": reply, "metrics": m})

        router_p = sum(r.prompt_tokens for r in m.api_calls if r.purpose == "router")
        router_c = sum(r.completion_tokens for r in m.api_calls if r.purpose == "router")
        escalated = escalated or any(tc["name"] == "create_ticket" for tc in m.tool_calls)
        totals["p"] += m.prompt_tokens
        totals["c"] += m.completion_tokens
        totals["router"] += router_p + router_c
        totals["latency"] += m.latency_ms

        turn_row = {
            "scenario": sid, "agent": agent_name, "run": run_no, "turn": turn,
            "customer_msg": customer_msg, "agent_msg": reply,
            "latency_ms": round(m.latency_ms, 1),
            "prompt_tokens": m.prompt_tokens, "completion_tokens": m.completion_tokens,
            "total_tokens": m.total_tokens, "api_calls": len(m.api_calls),
            "router_prompt_tokens": router_p, "router_completion_tokens": router_c,
            "customer_tokens": 0,  # filled below once the sim replies
            "tool_calls": json.dumps([tc["name"] for tc in m.tool_calls]),
            "node": m.extra.get("node", ""), "router_fallback": m.extra.get("router_fallback", ""),
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
        jl.append({"type": "turn", **turn_row,
                   "tool_call_details": m.tool_calls, "path": m.extra.get("path", [])})

        if turn >= scenario["max_customer_turns"]:
            append_csv(PATHS["turns_csv"], TURN_FIELDS, turn_row)
            break

        customer_msg, cust_rec = sim.reply(history)
        totals["customer"] += cust_rec.total_tokens
        turn_row["customer_tokens"] = cust_rec.total_tokens
        append_csv(PATHS["turns_csv"], TURN_FIELDS, turn_row)

        r = end_reason(customer_msg)
        if r:
            reason = r
            break

    conv_row = {
        "scenario": sid, "agent": agent_name, "run": run_no,
        "turns": sum(1 for t in md_turns if t["role"] == "assistant"),
        "prompt_tokens": totals["p"], "completion_tokens": totals["c"],
        "total_tokens": totals["p"] + totals["c"], "router_tokens": totals["router"],
        "customer_tokens": totals["customer"],
        "latency_ms_total": round(totals["latency"], 1),
        "end_reason": reason, "escalated": escalated,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    jl.append({"type": "end", **conv_row})

    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_jsonl.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in jl), encoding="utf-8")
    out_md.write_text(
        render_transcript_md(f"{agent_name} — {sid} run {run_no} ({reason})", md_turns),
        encoding="utf-8",
    )
    append_csv(PATHS["convs_csv"], CONV_FIELDS, conv_row)
    return conv_row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max conversations this session (0 = no cap)")
    ap.add_argument("--runs", type=int, default=config.RUNS_PER_SCENARIO)
    ap.add_argument("--agents", default="agent_a,agent_b")
    ap.add_argument("--scenarios", default="", help="comma-separated scenario ids (default: all)")
    ap.add_argument("--scenarios-file", default=str(config.ROOT / "simulation" / "scenarios.json"))
    ap.add_argument("--out-root", default="", help="alternate results root (e.g. results/stress)")
    args = ap.parse_args()

    if args.out_root:
        set_out_root(Path(args.out_root))

    scenarios = json.loads(Path(args.scenarios_file).read_text(encoding="utf-8"))
    if args.scenarios:
        want = set(args.scenarios.split(","))
        scenarios = [s for s in scenarios if s["id"] in want]
    agent_names = args.agents.split(",")

    snapshot_sources()
    PATHS["turns_csv"].parent.mkdir(parents=True, exist_ok=True)

    done = skipped = 0
    try:
        for run_no in range(1, args.runs + 1):
            for scenario in scenarios:
                # alternate which agent goes first per run (fairness vs time-of-day load)
                order = agent_names if run_no % 2 == 1 else list(reversed(agent_names))
                for agent_name in order:
                    out = PATHS["transcripts"] / agent_name / f"{scenario['id']}_run{run_no}.jsonl"
                    if out.exists():
                        skipped += 1
                        continue
                    if args.limit and done >= args.limit:
                        raise KeyboardInterrupt
                    row = run_conversation(agent_name, scenario, run_no)
                    done += 1
                    print(f"[{done}] {scenario['id']} {agent_name} run{run_no}: "
                          f"{row['turns']} turns, {row['total_tokens']} tokens, {row['end_reason']}")
    except KeyboardInterrupt:
        print("\nSession limit reached (or interrupted).")
    except RuntimeError as e:
        print(f"\nSTOPPED: {e}")
        print("Progress is saved. Re-run this script later to resume where it left off.")

    total = len(scenarios) * len(agent_names) * args.runs
    print(f"\nThis session: {done} new conversation(s), {skipped} already done. "
          f"Matrix progress: {skipped + done}/{total}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
