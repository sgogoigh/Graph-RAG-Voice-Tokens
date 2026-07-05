"""H4 stress test: degradation analysis + figures + STRESS_H4.md.

The H4 question: does quality degrade with conversation depth, and does the monolithic
architecture degrade FASTER? Signals:
  1. Resolution rate by goal POSITION (1..8) per agent — the headline chart.
  2. Per-goal score by position (softer, continuous version).
  3. Prompt tokens per turn by turn index (1..26) — the cost-growth mechanics.
  4. Latency per turn by turn index.
Plus a summary table: early (goals 1-3) vs late (goals 6+) resolution and score, with
the early→late delta per agent.

Reads  results/stress/metrics/turns.csv + results/stress/qc/goal_scores.jsonl
Writes results/stress/figures/*.png + results/stress/STRESS_H4.md

Run:  .venv/Scripts/python analysis/stress_analysis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

import config  # noqa: E402
from analysis.visualize import AGENTS, COL, INK2, LABEL, _style  # noqa: E402  (shared palette + rcParams side-effect)

STRESS_ROOT = config.RESULTS_DIR / "stress"
FIGS = STRESS_ROOT / "figures"


def _save(fig, name: str) -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGS / name, dpi=150)
    plt.close(fig)
    print(f"  wrote stress/figures/{name}")


def fig_resolution_by_position(goals: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for agent in AGENTS:
        g = goals[goals["agent"] == agent]
        if g.empty:
            continue
        rate = g.groupby("goal")["resolved"].mean()
        ax.plot(rate.index, rate * 100, color=COL[agent], linewidth=2, marker="o",
                markersize=5, label=LABEL[agent])
    _style(ax, "Resolution rate by issue position (the H4 degradation curve)",
           "issue position in the conversation", "% of issues resolved")
    ax.set_ylim(0, 105)
    ax.set_xticks(sorted(goals["goal"].unique()))
    ax.legend(loc="lower left")
    _save(fig, "figS1_resolution_by_position.png")


def fig_score_by_position(goals: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for agent in AGENTS:
        g = goals[goals["agent"] == agent]
        if g.empty:
            continue
        med = g.groupby("goal")["score"].median()
        ax.plot(med.index, med, color=COL[agent], linewidth=2, marker="o",
                markersize=5, label=LABEL[agent])
    _style(ax, "Median per-issue handling score by position",
           "issue position in the conversation", "score (0-100)")
    ax.set_ylim(0, 105)
    ax.set_xticks(sorted(goals["goal"].unique()))
    ax.legend(loc="lower left")
    _save(fig, "figS2_score_by_position.png")


def fig_tokens_by_turn(turns: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for agent in AGENTS:
        g = turns[turns["agent"] == agent]
        if g.empty:
            continue
        med = g.groupby("turn")["prompt_tokens"].median()
        ax.plot(med.index, med, color=COL[agent], linewidth=2, label=LABEL[agent])
    _style(ax, "Prompt tokens per turn as the conversation deepens",
           "customer turn", "prompt tokens / turn (median)")
    ax.legend(loc="upper left")
    _save(fig, "figS3_prompt_tokens_by_turn.png")


def fig_latency_by_turn(turns: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for agent in AGENTS:
        g = turns[turns["agent"] == agent]
        if g.empty:
            continue
        med = g.groupby("turn")["latency_ms"].median() / 1000
        ax.plot(med.index, med, color=COL[agent], linewidth=2, label=LABEL[agent])
    _style(ax, "Per-turn latency as the conversation deepens",
           "customer turn", "seconds per turn (median)")
    ax.legend(loc="upper left")
    _save(fig, "figS4_latency_by_turn.png")


def summarize(goals: pd.DataFrame, turns: pd.DataFrame, convs: pd.DataFrame) -> list[str]:
    lines = [
        "# H4 Stress Test — Long-Conversation Degradation (marathon scenarios)",
        "",
        "6 marathon scenarios (7-8 sequential issues each, up to 26 customer turns) × "
        "3 agents × 2 runs = 36 conversations. Per-goal blind judging (deduction rubric, "
        "double-judged, resolved = strict AND). Data: `results/stress/`.",
        "",
        "| Agent | convs | median turns | median tokens/conv | goals resolved | "
        "early res. (1-3) | late res. (6+) | early→late Δ | early score | late score |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for agent in AGENTS:
        g = goals[goals["agent"] == agent]
        c = convs[convs["agent"] == agent]
        if g.empty:
            continue
        early, late = g[g["goal"] <= 3], g[g["goal"] >= 6]
        er, lr = early["resolved"].mean(), late["resolved"].mean()
        lines.append(
            f"| {LABEL[agent]} | {len(c)} | {c['turns'].median():.0f} | "
            f"{c['total_tokens'].median():,.0f} | {g['resolved'].mean():.0%} | "
            f"{er:.0%} | {lr:.0%} | **{(lr - er) * 100:+.0f}pp** | "
            f"{early['score'].median():.0f} | {late['score'].median():.0f} |"
        )
    lines += [
        "",
        "![Resolution by position](figures/figS1_resolution_by_position.png)",
        "",
        "![Score by position](figures/figS2_score_by_position.png)",
        "",
        "![Tokens by turn](figures/figS3_prompt_tokens_by_turn.png)",
        "",
        "![Latency by turn](figures/figS4_latency_by_turn.png)",
        "",
        "## Reading",
        "_(verdict authored after data review)_",
    ]
    return lines


def main() -> int:
    turns = pd.read_csv(STRESS_ROOT / "metrics" / "turns.csv")
    convs = pd.read_csv(STRESS_ROOT / "metrics" / "conversations.csv")
    goals = pd.DataFrame([json.loads(x) for x in
                          (STRESS_ROOT / "qc" / "goal_scores.jsonl").read_text(encoding="utf-8").splitlines()
                          if x.strip()])
    print(f"{len(convs)} conversations, {len(turns)} turns, {len(goals)} goal judgments")

    fig_resolution_by_position(goals)
    fig_score_by_position(goals)
    fig_tokens_by_turn(turns)
    fig_latency_by_turn(turns)

    out = STRESS_ROOT / "STRESS_H4.md"
    out.write_text("\n".join(summarize(goals, turns, convs)), encoding="utf-8")
    print(f"  wrote {out.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
