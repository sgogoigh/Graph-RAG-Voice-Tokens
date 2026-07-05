"""M9/M15: figures + REPORT.md generator (PLAN.md §11, P2.3) — three-way A/B/C.

Reads results/metrics/turns.csv + conversations.csv + results/qc/scores.jsonl and writes
results/figures/*.png plus a data-complete REPORT.md at the repo root.

Chart conventions (dataviz method, reference palette):
- Fixed categorical slots: Agent A = blue #2a78d6, Agent B = aqua #1baf7a,
  Agent C = yellow #eda100. Color follows the entity everywhere.
- Light surface #fcfcfb, hairline grid #e1e0d9, baseline #c3c2b7, muted ink #898781.
- Aqua and yellow are sub-3:1 on the light surface -> relief rule: direct value labels
  on key marks + full tables in REPORT.md.

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

AGENTS = ["agent_a", "agent_b", "agent_c"]
COL = {"agent_a": "#2a78d6", "agent_b": "#1baf7a", "agent_c": "#eda100"}
LABEL = {"agent_a": "Agent A (monolithic prompt)", "agent_b": "Agent B (graph-RAG)",
         "agent_c": "Agent C (vector RAG)"}
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


def _agents_in(df: pd.DataFrame) -> list[str]:
    return [a for a in AGENTS if a in set(df["agent"])]


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
    for agent in _agents_in(turns):
        g = turns[turns["agent"] == agent].copy()
        g["cum"] = g.sort_values("turn").groupby(["scenario", "run"])["total_tokens"].cumsum()
        stats = g.groupby("turn")["cum"].agg(["median", lambda s: s.quantile(0.25),
                                              lambda s: s.quantile(0.75)])
        stats.columns = ["med", "q1", "q3"]
        ax.plot(stats.index, stats["med"], color=COL[agent], linewidth=2, label=LABEL[agent])
        ax.fill_between(stats.index, stats["q1"], stats["q3"], color=COL[agent], alpha=0.13,
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
    agents = _agents_in(turns)
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    med = turns.groupby(["agent", "turn"])["prompt_tokens"].median().unstack(0)
    x = med.index.to_numpy()
    width = 0.84 / max(1, len(agents))
    for i, agent in enumerate(agents):
        if agent not in med:
            continue
        offs = (i - (len(agents) - 1) / 2) * width
        bars = ax.bar(x + offs, med[agent], width * 0.92, color=COL[agent],
                      label=LABEL[agent], zorder=3)
        for b in bars:  # direct labels: relief rule for aqua/yellow, symmetry for blue
            if b.get_height() > 0:
                ax.annotate(f"{b.get_height()/1000:.1f}k", (b.get_x() + b.get_width() / 2,
                            b.get_height()), ha="center", va="bottom", fontsize=7, color=INK2)
    _style(ax, "Median prompt tokens per turn (the fixed-overhead picture)",
           "customer turn", "prompt tokens / turn")
    ax.set_xticks(x)
    ax.legend(loc="upper right")
    _save(fig, "fig2_turn_prompt_tokens.png")


def fig_latency(turns: pd.DataFrame) -> None:
    agents = _agents_in(turns)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    data = [turns.loc[turns["agent"] == a, "latency_ms"] / 1000 for a in agents]
    bp = ax.boxplot(data, tick_labels=[LABEL[a] for a in agents], widths=0.45,
                    patch_artist=True, showfliers=False, medianprops={"color": INK, "linewidth": 1.4})
    for patch, agent in zip(bp["boxes"], agents):
        patch.set_facecolor(COL[agent])
        patch.set_alpha(0.55)
        patch.set_edgecolor(COL[agent])
    for i, series in enumerate(data, start=1):
        ax.annotate(f"median {series.median():.1f}s", (i + 0.26, series.median()),
                    textcoords="offset points", xytext=(8, -4), color=INK2, fontsize=9)
    _style(ax, "Per-turn wall-clock latency (tool loop; B incl. routing, C incl. retrieval)",
           "", "seconds per turn")
    _save(fig, "fig3_latency.png")


def fig_qc(scores: pd.DataFrame) -> None:
    agents = _agents_in(scores)
    dims = ["task_resolution", "factual_accuracy", "policy_compliance",
            "conversational_quality", "efficiency", "composite"]
    fig, ax = plt.subplots(figsize=(8.8, 4.2))
    med = scores.groupby("agent")[dims].median()
    x = pd.RangeIndex(len(dims)).to_numpy()
    width = 0.84 / max(1, len(agents))
    for i, agent in enumerate(agents):
        if agent not in med.index:
            continue
        offs = (i - (len(agents) - 1) / 2) * width
        bars = ax.bar(x + offs, med.loc[agent, dims], width * 0.92,
                      color=COL[agent], label=LABEL[agent], zorder=3)
        for b in bars:
            ax.annotate(f"{b.get_height():.0f}", (b.get_x() + b.get_width() / 2, b.get_height()),
                        ha="center", va="bottom", fontsize=7.5, color=INK2)
    _style(ax, "Q-C rubric scores (median across conversations)", "", "score (0-100)")
    ax.set_xticks(x)
    ax.set_xticklabels([d.replace("_", "\n") for d in dims], fontsize=8.5)
    ax.set_ylim(0, 110)
    ax.legend(loc="lower right", fontsize=8.5)
    _save(fig, "fig4_qc_scores.png")


def fig_frontier(convs: pd.DataFrame, scores: pd.DataFrame) -> None:
    merged = convs.merge(scores[["scenario", "agent", "run", "composite"]],
                         on=["scenario", "agent", "run"], how="inner")
    if merged.empty:
        return
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    for agent in _agents_in(merged):
        g = merged[merged["agent"] == agent]
        ax.scatter(g["total_tokens"] / 1000, g["composite"], s=42, color=COL[agent],
                   alpha=0.75, edgecolors=SURFACE, linewidths=1.2, label=LABEL[agent], zorder=3)
    _style(ax, "Efficiency frontier: conversation cost vs judged quality",
           "total tokens per conversation (thousands)", "Q-C composite")
    ax.legend(loc="lower right")
    _save(fig, "fig5_frontier.png")


def summarize(turns: pd.DataFrame, convs: pd.DataFrame, scores: pd.DataFrame) -> dict:
    s: dict = {}
    for agent in _agents_in(convs):
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
            "qc_composite": (scores.loc[scores["agent"] == agent, "composite"].median()
                             if not scores.empty and agent in set(scores["agent"]) else None),
        }
        if agent != "agent_a" and "agent_a" in s:
            row["savings_vs_a"] = 100 * (1 - row["median_tokens_per_conv"]
                                         / s["agent_a"]["median_tokens_per_conv"])
        s[agent] = row
    return s


def _fmt_qc(v) -> str:
    return "—" if v is None else f"{v:.0f}"


def write_report(s: dict, scores: pd.DataFrame) -> None:
    from datetime import date
    a, b, c = s.get("agent_a"), s.get("agent_b"), s.get("agent_c")

    def row(label: str, fmt) -> str:
        cells = [fmt(x) if x else "—" for x in (a, b, c)]
        return f"| {label} | " + " | ".join(cells) + " |"

    lines = [
        "# Graph-RAG vs Monolithic Prompt vs Vector RAG — Results Report",
        "",
        f"Generated by `analysis/visualize.py` on {date.today().isoformat()}. Setup: PLAN.md "
        "(Phase 1 §1-13, Phase 2 P2.*); parity evidence: `results/parity_matrix.csv` (3-way) + "
        f"`results/semantic_parity_triage.md`. All agents ran `{config.AGENT_MODEL}` "
        f"(temp {config.AGENT_TEMPERATURE}); B's router: `{config.ROUTER_MODEL}` (billed to B); "
        f"C: hybrid vector+BM25 retrieval, k={config.RAG_TOP_K} (local, ~0 tokens); "
        f"judge: `{config.JUDGE_MODEL}`, blind, double-judged, per-dimension medians.",
        "",
        "## Headline numbers",
        "",
        "| Metric | Agent A (monolithic) | Agent B (graph-RAG) | Agent C (vector RAG) |",
        "|---|---|---|---|",
        row("Conversations", lambda x: str(x["conversations"])),
        row("Median tokens / conversation",
            lambda x: f"{x['median_tokens_per_conv']:,.0f}"
                      + (f" ({x['savings_vs_a']:.0f}% less than A)" if "savings_vs_a" in x else "")),
        row("Median prompt tokens / turn", lambda x: f"{x['median_prompt_per_turn']:,.0f}"),
        row("Median / p90 turn latency",
            lambda x: f"{x['median_latency_s']:.1f}s / {x['p90_latency_s']:.1f}s"),
        row("Q-C composite (median)", lambda x: _fmt_qc(x["qc_composite"])),
        row("Resolution rate (ended satisfied)", lambda x: f"{x['resolution_rate']:.0%}"),
        row("Escalated to human (ticket)", lambda x: f"{x['escalation_rate']:.0%}"),
        "",
    ]
    if b:
        lines.append(f"Agent B's routing overhead: **{b['router_share']:.1%}** of its total tokens "
                     "(honestly billed). Agent C's retrieval is local (~0 LLM tokens; wall-clock "
                     "included in its latency).")
    lines += [
        "",
        "## Figures",
        "",
        "![Cumulative token growth](results/figures/fig1_cumulative_tokens.png)",
        "",
        "![Per-turn prompt tokens](results/figures/fig2_turn_prompt_tokens.png)",
        "",
        "![Latency](results/figures/fig3_latency.png)",
        "",
        "![Q-C scores](results/figures/fig4_qc_scores.png)",
        "",
        "![Efficiency frontier](results/figures/fig5_frontier.png)",
        "",
        "## Hypotheses",
        "",
    ]

    if a and b:
        sav_b = b.get("savings_vs_a", 0)
        lines.append(f"- **H1 (B tokens):** {'SUPPORTED' if sav_b >= 40 else 'NOT MET'} — "
                     f"{sav_b:.0f}% median reduction vs A (target ≥40%).")
        lines.append(f"- **H2 (B latency):** {'SUPPORTED' if b['median_latency_s'] <= a['median_latency_s'] else 'NOT MET'} — "
                     f"B {b['median_latency_s']:.2f}s vs A {a['median_latency_s']:.2f}s per turn.")
        qa, qb = a["qc_composite"], b["qc_composite"]
        if qa is not None and qb is not None:
            lines.append(f"- **H3 (B quality):** {'SUPPORTED' if qb >= qa else 'NOT MET'} — "
                         f"B composite {qb:.1f} vs A {qa:.1f}.")
    lines.append("- **H4 (degradation):** INCONCLUSIVE at ≤6-turn conversations — see Phase-1 discussion.")
    if b and c:
        near = abs(c["median_tokens_per_conv"] - b["median_tokens_per_conv"]) \
               / b["median_tokens_per_conv"] <= 0.25
        lines.append(f"- **H5 (C tokens ≈ B):** {'SUPPORTED' if near else 'NOT MET'} — "
                     f"C {c['median_tokens_per_conv']:,.0f} vs B {b['median_tokens_per_conv']:,.0f} "
                     "median tokens/conversation (both turn-scoped, both ≪ A).")
        qb, qc = b["qc_composite"], c["qc_composite"]
        if qb is not None and qc is not None:
            lines.append(f"- **H6 (structure buys quality):** {'SUPPORTED' if qb > qc else 'NOT MET'} — "
                         f"B composite {qb:.1f} vs C {qc:.1f}; see edge-case breakdown in Discussion.")
        lines.append(f"- **H7 (C latency < B):** {'SUPPORTED' if c['median_latency_s'] < b['median_latency_s'] else 'NOT MET'} — "
                     f"C {c['median_latency_s']:.2f}s vs B {b['median_latency_s']:.2f}s per turn.")
    lines += ["", "## Discussion", "",
              "_(Three-way narrative authored after data review — Phase-1 A-vs-B discussion "
              "is preserved in git history; the final version covers B-vs-C edge-case analysis, "
              "guardrail-recall findings, and threats to validity.)_", ""]

    (config.ROOT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
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
