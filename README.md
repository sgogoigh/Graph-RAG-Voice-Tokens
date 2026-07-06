# Graph-RAG-Voice-Tokens

Does graph-structured RAG actually reduce tokens/compute — and what does it buy beyond cost?
This repo is a controlled, fully-instrumented experiment comparing three customer-support agents
for a hypothetical clothing store ("Loomora"), built on the **same machine-audited knowledge base**:

| Arm | Architecture | Context per turn |
|---|---|---|
| **Agent A** | Monolithic system prompt | Entire ~2,800-word policy manual, every call |
| **Agent B** | Graph-RAG | LLM router walks a 42-node / 83-edge workflow graph; only the active node's instruction packet is injected (turn-scoped) |
| **Agent C** | Vanilla vector RAG | Top-3 chunks from a byte-identical corpus (ChromaDB + BM25 hybrid, RRF-fused) |

Measured across 342 simulated conversations: **tokens, latency, and blind-judged quality**, with
B's router overhead honestly billed to B. Headline: turn-scoping halves tokens (−53% B, −51% C),
graph structure alone buys policy correctness and near-flat quality in marathon conversations.

Full design: [PLAN.md](PLAN.md) · scenario ground truth: [Checklist.md](Checklist.md)

## Setup

Requires Python 3.10+. From the repo root:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows (POSIX: .venv/bin/python)
```

Create `.env` in the repo root with the API key(s) for the providers you use:

```
MISTRAL_API_KEY=...     # default: all roles run mistral/mistral-small-2506
GROQ_API_KEY=...        # used for the gpt-oss-120b QC cross-check / semantic parity judge
GEMINI_API_KEY=...      # optional; only if you switch models to a gemini/ prefix
```

All models, paths, policies, and knobs live in [config.py](config.py) — the single source of
truth. Model strings route by prefix (`mistral/`, `gemini/`, otherwise Groq).

## How to run

All commands use `.venv/Scripts/python` from the repo root. Steps 1–4 are cheap sanity gates;
5–7 are the real experiment; 8–9 are the extra studies.

```bash
# 1. Connectivity + tool-calling smoke (one call per configured model)
.venv/Scripts/python smoke_test.py

# 2. Seed the deterministic database (asserts every Checklist data dependency)
.venv/Scripts/python db/seed.py

# 3. Validate the knowledge sources
.venv/Scripts/python graph/validate.py           # graph structure invariants
.venv/Scripts/python graph/probe_router.py       # 12 router-decision probes
.venv/Scripts/python rag/build_corpus.py         # derive C's corpus (byte-parity with A's manual)
.venv/Scripts/python rag/chunker.py              # section-aware chunking -> rag/chunks.jsonl
.venv/Scripts/python rag/store.py                # build the Chroma index
.venv/Scripts/python rag/probe_retrieval.py      # 13 retrieval probes + k-ablation
.venv/Scripts/python analysis/parity_audit.py    # 3-way tag audit -> results/parity_matrix.csv
.venv/Scripts/python analysis/semantic_parity.py # LLM cross-review of knowledge parity

# 4. Per-agent scripted smoke conversations (transcripts -> results/transcripts/<agent>/)
.venv/Scripts/python agents/smoke_agent_a.py
.venv/Scripts/python agents/smoke_agent_b.py
.venv/Scripts/python agents/smoke_agent_c.py

# 5. Main matrix: 51 scenarios x 3 agents x 2 runs (resumable — rerun to continue)
.venv/Scripts/python simulation/run_experiments.py --agents agent_a,agent_b,agent_c
#   useful flags: --limit N   --runs N   --scenarios S-V1-01,S-V2-02   --out-root results/foo

# 6. Blind quality judging (double-judged, tie-broken; --crosscheck N adds gpt-oss-120b)
.venv/Scripts/python analysis/qc_judge.py --crosscheck 30

# 7. Figures + REPORT.md
.venv/Scripts/python analysis/visualize.py

# 8. H4 stress test (marathon conversations, 7-8 issues each)
.venv/Scripts/python simulation/run_experiments.py --agents agent_a,agent_b,agent_c \
    --scenarios-file simulation/stress_scenarios.json --out-root results/stress
.venv/Scripts/python analysis/stress_judge.py      # per-goal judging
.venv/Scripts/python analysis/stress_analysis.py   # figures + STRESS_H4.md

# 9. Speculative-routing latency experiment (serial B vs speculative B, same script)
.venv/Scripts/python agents/smoke_agent_b.py
.venv/Scripts/python agents/smoke_agent_b_spec.py
```

**Parity rule:** after ANY edit to `agents/prompts/*`, `graph/graph.json`, or the RAG chunks,
re-run step 3 before trusting new results — no arm may know anything the others don't.

## Repo layout

```
config.py               single source of truth (models, policies, paths)
db/                     schema + deterministic seed (7 tables, asserted ground truth)
agents/                 A/B/C implementations, prompts, multi-provider LLM client, 10 DB tools
graph/                  workflow graph (graph.json), router engine, validators/probes
rag/                    corpus derivation, chunker, hybrid vector+BM25 store, probes
simulation/             scenarios (51 + 6 marathons), customer personas, experiment harness
analysis/               judges, parity audits, visualization/report generators
results/                transcripts, per-turn metrics CSVs, QC scores, figures, reports
docs/                   research proposal + Veo integration note (.docx + generators)
```

## Reports — what you'll find at the end

- **[REPORT.md](REPORT.md)** — the main three-way results report (auto-generated by
  `analysis/visualize.py`, then hand-annotated). Headline table, five figures, verdicts on all
  seven hypotheses, and the discussion. Short version: **H1/H3/H5/H6 supported, H2/H7 not met**
  — B cuts tokens 53% at equal-or-better judged quality (90 vs 88); C matches B's cost but not
  its policy discipline; A remains the raw-latency winner (1.1 s vs ~1.65 s) because it makes
  zero pre-generation calls.
- **[results/stress/STRESS_H4.md](results/stress/STRESS_H4.md)** — the marathon degradation
  study (H4). Early→late resolution drops −31 pp for A (score 85→68) vs **−22 pp for B
  (85→84)**; C's −32 pp at B-like token cost isolates the mechanism: degradation comes from
  instruction relevance decaying at depth, not context volume. A's marathons cost 2.1× more
  (86.9k vs ~40k median tokens).
- **[results/spec_router/SPEC_ROUTER.md](results/spec_router/SPEC_ROUTER.md)** — can B's router
  latency be hidden? Not by caching state (already free) — but speculative parallel routing
  works: median 1.90→1.70 s/turn on the paired suite at +15% tokens; projected ≈ −0.15 s/turn
  for ≈ +9% tokens at matrix stay-rates, with a hard no-side-effect guard on write-capable nodes.
- **[results/parity_matrix.csv](results/parity_matrix.csv)** +
  **[results/semantic_parity_triage.md](results/semantic_parity_triage.md)** — the no-bias
  evidence: per-scenario machine audit that A's anchors, B's nodes, and C's chunks all cover the
  same knowledge, plus the triaged LLM cross-review (including the documented case of a judge
  model fabricating findings — caught and pinned to a second model family).
- **[docs/Research_Proposal_GraphRAG.docx](docs/Research_Proposal_GraphRAG.docx)** — the full
  research proposal write-up: objectives, 22-source literature review, methodology, experiments,
  results with figures, limitations, bibliography.
- **[docs/Veo_Integration_Note.docx](docs/Veo_Integration_Note.docx)** — bridge document
  connecting these findings with the Prompt-Orchestrator scene-graph pipeline to supplement
  video generation (Veo 3.1): routed turn-scoped packets per shot, speculative shot pipelining,
  and a proposed three-arm validation mirroring this experiment.
- **Raw artifacts** — every conversation transcript (`results/transcripts/`, .md + .jsonl),
  per-turn/per-conversation metrics (`results/metrics/*.csv`), judge scores (`results/qc/`),
  figures (`results/figures/`, `results/stress/figures/`), and prompt/graph hash snapshots
  (`results/prompt_snapshots/`) for reproducibility.
