"""M9: figures + REPORT.md generator (PLAN.md §11).

Reads results/metrics/turns.csv + conversations.csv + results/qc/scores.jsonl and writes
results/figures/*.png plus a data-complete REPORT.md at the repo root.

Chart conventions (dataviz method, reference palette):
- Agent A = categorical slot 1 (blue #2a78d6), Agent B = slot 2 (aqua #1baf7a),
  fixed assignment everywhere - color follows the entity.
- Light surface #fcfcfb, hairline grid #e1e0d9, baseline #c3c2b7, muted ink #898781.
- Thin marks, one axis per chart, legend for the two series, direct labels on key
  marks (aqua is sub-3:1 on light surface - the relief rule), tables in REPORT.md.

Run:  .venv/Scripts/python analysis/visualize.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402

# reference palette roles
COL = {"agent_a": "#2a78d6", "agent_b": "#1baf7a"}
LABEL = {"agent_a": "Agent A (monolithic prompt)", "agent_b": "Agent B (graph-RAG)"}
SURFACE, GRID, BASELINE = "#fcfcfb", "#e1e0d9", "#c3c2b7"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "sans-serif", "font.size": 10,
    "text.color": INK, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": BASELINE, "axes.linewidth": 1.0,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "legend.frameon": False,
})


def _style(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title, color=INK, fontsize=11, loc="left", pad=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="x", visible=False)


def _save(fig, name: str) -> None:
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / name, dpi=150)
    plt.close(fig)
    print(f"  wrote figures/{name}")


def fig_cumulative(turns: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for agent, g in turns.groupby("agent"):
        g = g.copy()
        g["cum"] = g.sort_values("turn").groupby(["scenario", "run"])["total_tokens"].cumsum()
        stats = g.groupby("turn")["cum"].agg(["median", lambda s: s.quantile(0.25),
                                              lambda s: s.quantile(0.75)])
        stats.columns = ["med", "q1", "q3"]
        ax.plot(stats.index, stats["med"], color=COL[agent], linewidth=2, label=LABEL[agent])
        ax.fill_between(stats.index, stats["q1"], stats["q3"], color=COL[agent], alpha=0.15,
                        linewidth=0)
        last = stats.iloc[-1]
        ax.annotate(f"{last['med']/1000:.0f}k", (stats.index[-1], last["med"]),
                    textcoords="offset points", xytext=(6, -2), color=INK2, fontsize=9)
    _style(ax, "Cumulative tokens per conversation (median, IQR band)",
           "customer turn", "cumulative tokens")
    ax.set_xticks(sorted(turns["turn"].unique()))
    ax.legend(loc="upper left")
    _save(fig, "fig1_cumulative_tokens.png")


def fig_turn_tokens(turns: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    med = turns.groupby(["agent", "turn"])["prompt_tokens"].median().unstack(0)
    x = med.index.to_numpy()
    width = 0.42
    for i, agent in enumerate(["agent_a", "agent_b"]):
        if agent not in med:
            continue
        bars = ax.bar(x + (i - 0.5) * width, med[agent], width * 0.94, color=COL[agent],
                      label=LABEL[agent], zorder=3)
        for b in bars:  # direct labels: relief rule for the aqua series, symmetry for blue
            if b.get_height() > 0:
                ax.annotate(f"{b.get_height()/1000:.1f}k", (b.get_x() + b.get_width() / 2,
                            b.get_height()), ha="center", va="bottom", fontsize=7.5, color=INK2)
    _style(ax, "Median prompt tokens per turn (the fixed-overhead picture)",
           "customer turn", "prompt tokens / turn")
    ax.set_xticks(x)
    ax.legend(loc="upper right")
    _save(fig, "fig2_turn_prompt_tokens.png")


def fig_latency(turns: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    data = [turns.loc[turns["agent"] == a, "latency_ms"] / 1000 for a in ["agent_a", "agent_b"]]
    bp = ax.boxplot(data, tick_labels=[LABEL["agent_a"], LABEL["agent_b"]], widths=0.45,
                    patch_artist=True, showfliers=False, medianprops={"color": INK, "linewidth": 1.4})
    for patch, agent in zip(bp["boxes"], ["agent_a", "agent_b"]):
        patch.set_facecolor(COL[agent])
        patch.set_alpha(0.55)
        patch.set_edgecolor(COL[agent])
    for i, series in enumerate(data, start=1):
        ax.annotate(f"median {series.median():.1f}s", (i + 0.26, series.median()),
                    textcoords="offset points", xytext=(8, -4), color=INK2, fontsize=9)
    _style(ax, "Per-turn wall-clock latency (includes tool loop; B includes routing)",
           "", "seconds per turn")
    _save(fig, "fig3_latency.png")


def fig_qc(scores: pd.DataFrame) -> None:
    dims = ["task_resolution", "factual_accuracy", "policy_compliance",
            "conversational_quality", "efficiency", "composite"]
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    med = scores.groupby("agent")[dims].median()
    x = pd.RangeIndex(len(dims)).to_numpy()
    width = 0.42
    for i, agent in enumerate(["agent_a", "agent_b"]):
        if agent not in med.index:
            continue
        bars = ax.bar(x + (i - 0.5) * width, med.loc[agent, dims], width * 0.94,
                      color=COL[agent], label=LABEL[agent], zorder=3)
        for b in bars:
            ax.annotate(f"{b.get_height():.0f}", (b.get_x() + b.get_width() / 2, b.get_height()),
                        ha="center", va="bottom", fontsize=8, color=INK2)
    _style(ax, "Q-C rubric scores (median across conversations)", "", "score (0-100)")
    ax.set_xticks(x)
    ax.set_xticklabels([d.replace("_", "\n") for d in dims], fontsize=8.5)
    ax.set_ylim(0, 108)
    ax.legend(loc="lower right")
    _save(fig, "fig4_qc_scores.png")


def fig_frontier(convs: pd.DataFrame, scores: pd.DataFrame) -> None:
    merged = convs.merge(scores[["scenario", "agent", "run", "composite"]],
                         on=["scenario", "agent", "run"], how="inner")
    if merged.empty:
        return
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for agent, g in merged.groupby("agent"):
        ax.scatter(g["total_tokens"] / 1000, g["composite"], s=42, color=COL[agent],
                   alpha=0.75, edgecolors=SURFACE, linewidths=1.2, label=LABEL[agent], zorder=3)
    _style(ax, "Efficiency frontier: conversation cost vs judged quality",
           "total tokens per conversation (thousands)", "Q-C composite")
    ax.legend(loc="lower right")
    _save(fig, "fig5_frontier.png")


def summarize(turns: pd.DataFrame, convs: pd.DataFrame, scores: pd.DataFrame) -> dict:
    s: dict = {}
    for agent in ["agent_a", "agent_b"]:
        c, t = convs[convs["agent"] == agent], turns[turns["agent"] == agent]
        row = {
            "conversations": len(c),
            "median_tokens_per_conv": c["total_tokens"].median(),
            "median_prompt_per_turn": t["prompt_tokens"].median(),
            "median_latency_s": t["latency_ms"].median() / 1000,
            "p90_latency_s": t["latency_ms"].quantile(0.9) / 1000,
            "resolution_rate": (c["end_reason"] == "satisfied").mean(),
            "escalation_rate": c["escalated"].astype(str).str.lower().eq("true").mean(),
            "router_share": (c["router_tokens"].sum() / c["total_tokens"].sum()) if agent == "agent_b" else 0.0,
        }
        if not scores.empty and agent in scores["agent"].values:
            row["qc_composite"] = scores.loc[scores["agent"] == agent, "composite"].median()
        s[agent] = row
    if s["agent_a"]["median_tokens_per_conv"]:
        s["token_savings_pct"] = 100 * (1 - s["agent_b"]["median_tokens_per_conv"]
                                        / s["agent_a"]["median_tokens_per_conv"])
    return s


REPORT_TEMPLATE = """# Graph-RAG vs Monolithic Prompt — Results Report

Generated by `analysis/visualize.py` on {date}. Setup: PLAN.md; parity evidence:
`results/parity_matrix.csv` + `results/semantic_parity_triage.md`. Both agents ran
`{agent_model}` (temp {temp}); Agent B's router: `{router_model}` (billed to B);
judge: `{judge_model}`, blind, double-judged, per-dimension medians.

## Headline numbers

| Metric | Agent A (monolithic) | Agent B (graph-RAG) |
|---|---|---|
| Conversations completed | {a_n} | {b_n} |
| Median tokens / conversation | {a_tok:,.0f} | {b_tok:,.0f} (**{savings:.0f}% less**) |
| Median prompt tokens / turn | {a_ppt:,.0f} | {b_ppt:,.0f} |
| Median / p90 turn latency | {a_lat:.1f}s / {a_p90:.1f}s | {b_lat:.1f}s / {b_p90:.1f}s |
| Q-C composite (median) | {a_qc} | {b_qc} |
| Resolution rate (ended satisfied) | {a_res:.0%} | {b_res:.0%} |
| Escalated to human (ticket) | {a_esc:.0%} | {b_esc:.0%} |

Agent B's routing overhead: **{router_share:.1%}** of its total tokens (honestly billed).

## Figures

![Cumulative token growth](results/figures/fig1_cumulative_tokens.png)

![Per-turn prompt tokens](results/figures/fig2_turn_prompt_tokens.png)

![Latency](results/figures/fig3_latency.png)

![Q-C scores](results/figures/fig4_qc_scores.png)

![Efficiency frontier](results/figures/fig5_frontier.png)

## Hypotheses (PLAN.md §1.3)

- **H1 (tokens):** {h1}
- **H2 (latency):** {h2}
- **H3 (quality):** {h3}
- **H4 (degradation):** see fig1/fig3 slopes — narrative in §Discussion.

## Discussion

_(Narrative analysis, transcript excerpts, and threats to validity are authored after
data review — see repository history for the finalized version.)_
"""


def write_report(s: dict, scores: pd.DataFrame) -> None:
    from datetime import date
    a, b = s["agent_a"], s["agent_b"]
    savings = s.get("token_savings_pct", 0.0)
    qc_a, qc_b = a.get("qc_composite"), b.get("qc_composite")
    h1 = (f"SUPPORTED — {savings:.0f}% median token reduction (target ≥40%)"
          if savings >= 40 else f"NOT MET — {savings:.0f}% reduction (target ≥40%)")
    h2 = ("SUPPORTED — B's median turn latency ≤ A's"
          if b["median_latency_s"] <= a["median_latency_s"] else
          "NOT MET — B slower per turn (routing adds a serial call)")
    h3 = ("PENDING — run analysis/qc_judge.py first" if qc_a is None or qc_b is None else
          (f"SUPPORTED — B composite {qc_b:.0f} ≥ A {qc_a:.0f}" if qc_b >= qc_a
           else f"NOT MET — B composite {qc_b:.0f} < A {qc_a:.0f}"))
    report = REPORT_TEMPLATE.format(
        date=date.today().isoformat(), agent_model=config.AGENT_MODEL,
        temp=config.AGENT_TEMPERATURE, router_model=config.ROUTER_MODEL,
        judge_model=config.JUDGE_MODEL,
        a_n=a["conversations"], b_n=b["conversations"],
        a_tok=a["median_tokens_per_conv"], b_tok=b["median_tokens_per_conv"], savings=savings,
        a_ppt=a["median_prompt_per_turn"], b_ppt=b["median_prompt_per_turn"],
        a_lat=a["median_latency_s"], a_p90=a["p90_latency_s"],
        b_lat=b["median_latency_s"], b_p90=b["p90_latency_s"],
        a_qc="—" if qc_a is None else f"{qc_a:.0f}", b_qc="—" if qc_b is None else f"{qc_b:.0f}",
        a_res=a["resolution_rate"], b_res=b["resolution_rate"],
        a_esc=a["escalation_rate"], b_esc=b["escalation_rate"],
        router_share=b["router_share"], h1=h1, h2=h2, h3=h3,
    )
    (config.ROOT / "REPORT.md").write_text(report, encoding="utf-8")
    print("  wrote REPORT.md")


def main() -> int:
    turns = pd.read_csv(config.METRICS_DIR / "turns.csv")
    convs = pd.read_csv(config.METRICS_DIR / "conversations.csv")
    scores_path = config.QC_DIR / "scores.jsonl"
    scores = (pd.DataFrame([json.loads(x) for x in scores_path.read_text(encoding="utf-8").splitlines() if x.strip()])
              if scores_path.exists() else pd.DataFrame())
    if not scores.empty:
        scores = scores[scores["judge_model"] == config.JUDGE_MODEL]  # cross-check rows excluded

    print(f"{len(convs)} conversations, {len(turns)} turns, {len(scores)} judged")
    fig_cumulative(turns)
    fig_turn_tokens(turns)
    fig_latency(turns)
    if not scores.empty:
        fig_qc(scores)
        fig_frontier(convs, scores)
    write_report(summarize(turns, convs, scores), scores)
    return 0


if __name__ == "__main__":
    sys.exit(main())
