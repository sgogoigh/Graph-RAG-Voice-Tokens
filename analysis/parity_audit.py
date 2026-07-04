"""M6 tag-level parity audit (PLAN.md §9.2) — offline, no API.

For every Checklist.md scenario, assert:
  A-side: every `A:` anchor literally appears in agents/prompts/agent_a_system.md
  B-side: every `B:` node id exists in graph/graph.json, AND the scenario id appears
          in the union of those nodes' `covers` tags (no phantom mappings)

Writes results/parity_matrix.csv and exits 1 on any gap.

Run:  .venv/Scripts/python analysis/parity_audit.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

ROW_RE = re.compile(
    r"^- \[[ x]\] (S-[A-Z0-9]+-\d+) \| (\S+) \| .*? \| Data: .*? \| A: (.*?) \| B: (.*)$",
    re.M,
)


def main() -> int:
    checklist = (config.ROOT / "Checklist.md").read_text(encoding="utf-8")
    prompt_a = (config.PROMPTS_DIR / "agent_a_system.md").read_text(encoding="utf-8")
    graph = json.loads(config.GRAPH_PATH.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in graph["nodes"]}

    rows = ROW_RE.findall(checklist)
    if not rows:
        print("FATAL: no scenario rows parsed from Checklist.md")
        return 1

    out_rows, gaps = [], 0
    for sid, direction, a_col, b_col in rows:
        anchors = [a.strip().lstrip("§") for a in a_col.split(",")]
        b_nodes = [b.strip() for b in b_col.split(",")]

        a_missing = [a for a in anchors if a not in prompt_a]
        b_missing = [b for b in b_nodes if b not in nodes]
        covers_union = {tag for b in b_nodes if b in nodes for tag in nodes[b].get("covers", [])}
        covers_ok = sid in covers_union

        ok = not a_missing and not b_missing and covers_ok
        gaps += not ok
        out_rows.append({
            "scenario": sid,
            "direction": direction,
            "a_anchors": "; ".join(anchors),
            "a_ok": not a_missing,
            "b_nodes": "; ".join(b_nodes),
            "b_ok": not b_missing,
            "b_covers_ok": covers_ok,
            "status": "OK" if ok else "GAP",
        })
        if not ok:
            detail = []
            if a_missing:
                detail.append(f"A missing anchors {a_missing}")
            if b_missing:
                detail.append(f"B missing nodes {b_missing}")
            if not covers_ok:
                detail.append("scenario not in B nodes' covers")
            print(f"GAP  {sid}: {'; '.join(detail)}")

    out = config.RESULTS_DIR / "parity_matrix.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    print(f"\n{len(out_rows)} scenarios audited -> {out}")
    if gaps:
        print(f"PARITY AUDIT FAILED: {gaps} gap(s)")
        return 1
    print("PARITY AUDIT PASSED: every scenario tagged on both sides.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
