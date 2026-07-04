"""Structural + coverage validation for graph.json (PLAN.md §8, SCHEMA.md invariants).

Checks (offline, no API):
  1. Unique ids; entry and globals exist; every edge target exists.
  2. Every node reachable from entry via edges ∪ entry_points ∪ globals.
  3. Non-terminal, non-guardrail nodes have >= 1 outgoing edge.
  4. Every node id in Checklist.md's `B:` column exists in the graph.
  5. Checklist scenario ids <-> node `covers` tags agree in BOTH directions.

Run:  .venv/Scripts/python graph/validate.py   (exit 1 on any failure)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

CHECKLIST = config.ROOT / "Checklist.md"
errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def main() -> int:
    data = json.loads(config.GRAPH_PATH.read_text(encoding="utf-8"))
    nodes = data["nodes"]
    ids = [n["id"] for n in nodes]
    by_id = {n["id"]: n for n in nodes}

    # 1. uniqueness + referential integrity
    for nid, count in Counter(ids).items():
        if count > 1:
            err(f"duplicate node id: {nid}")
    if data["entry"] not in by_id:
        err(f"entry node missing: {data['entry']}")
    for g in data["globals"]:
        if g not in by_id:
            err(f"global node missing: {g}")
    for n in nodes:
        for e in n["edges"]:
            if e["to"] not in by_id:
                err(f"{n['id']}: edge to unknown node '{e['to']}'")

    # 2. reachability from entry (edges + entry_points + globals are all legal moves)
    entry_points = [n["id"] for n in nodes if n.get("entry_point")]
    reachable = set()
    frontier = [data["entry"]]
    while frontier:
        nid = frontier.pop()
        if nid in reachable or nid not in by_id:
            continue
        reachable.add(nid)
        nxt = [e["to"] for e in by_id[nid]["edges"]] + entry_points + data["globals"]
        frontier += [x for x in nxt if x not in reachable]
    for nid in ids:
        if nid not in reachable:
            err(f"unreachable node: {nid}")

    # 3. no dead ends (terminal and guardrail nodes may rely on router/globals)
    for n in nodes:
        if n["type"] not in ("terminal",) and not n["edges"]:
            err(f"non-terminal node with no edges: {n['id']}")

    # 4+5. checklist cross-checks
    text = CHECKLIST.read_text(encoding="utf-8")
    scenario_rows = re.findall(r"- \[[ x]\] (S-[A-Z0-9]+-\d+) \|.*?\| B: ([^|\n]+)$", text, re.M)
    if not scenario_rows:
        err("could not parse any scenario rows from Checklist.md")
    checklist_ids = {sid for sid, _ in scenario_rows}

    for sid, bcol in scenario_rows:
        for node_ref in [x.strip() for x in bcol.split(",")]:
            if node_ref not in by_id:
                err(f"{sid}: B-column node '{node_ref}' not in graph")

    covered = set()
    for n in nodes:
        for tag in n.get("covers", []):
            covered.add(tag)
            if tag not in checklist_ids:
                err(f"{n['id']}: covers phantom scenario '{tag}'")
    for sid in sorted(checklist_ids - covered):
        err(f"scenario {sid} not covered by any node's `covers`")

    # report
    n_by_type = Counter(n["type"] for n in nodes)
    n_by_vert = Counter(n["vertical"] for n in nodes)
    print(f"graph.json: {len(nodes)} nodes, {sum(len(n['edges']) for n in nodes)} edges, "
          f"{len(entry_points)} entry points, {len(data['globals'])} globals")
    print(f"  by type: {dict(sorted(n_by_type.items()))}")
    print(f"  by vertical: {dict(sorted(n_by_vert.items()))}")
    print(f"  checklist: {len(checklist_ids)} scenarios parsed, {len(covered & checklist_ids)} covered")

    if errors:
        print(f"\nVALIDATION FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"  ✗ {e}")
        return 1
    print("\nVALIDATION PASSED — all invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
