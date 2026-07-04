"""Single source of truth for the Graph-RAG token-efficiency experiment.

Every script (agents, simulator, judge, analysis) imports from here so that
model choices, run counts, and paths can be changed in exactly one place.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "db" / "store.db"
GRAPH_PATH = ROOT / "graph" / "graph.json"
PROMPTS_DIR = ROOT / "agents" / "prompts"
RESULTS_DIR = ROOT / "results"
TRANSCRIPTS_DIR = RESULTS_DIR / "transcripts"
METRICS_DIR = RESULTS_DIR / "metrics"
QC_DIR = RESULTS_DIR / "qc"
FIGURES_DIR = RESULTS_DIR / "figures"

load_dotenv(ROOT / ".env")
GROQ_API_KEY = (os.getenv("GROQ_API_KEY") or "").strip()

# ---------------------------------------------------------------------------
# Models (PLAN.md §2 D2-D4) — all on Groq
# ---------------------------------------------------------------------------
# NOTE: model choice is constrained by Groq FREE-TIER limits (console.groq.com/docs/rate-limits):
#   llama-3.3-70b-versatile: 12k TPM / 100k TPD  -> one Agent A conversation ~28k, matrix infeasible
#   llama-3.1-8b-instant:     6k TPM             -> Agent A's ~6.3k-token request can't even be sent
#   llama-4-scout-17b:       30k TPM / 500k TPD / 1k RPD -> viable (RPD budgets the M7 matrix)
# The comparison stays valid because BOTH agents use the same model. Revisit on Dev Tier.
AGENT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # identical for Agent A and Agent B
ROUTER_MODEL = "llama-3.1-8b-instant"        # Agent B's graph router (billed to B)
CUSTOMER_MODEL = "llama-3.1-8b-instant"      # simulated customer
JUDGE_MODEL = "openai/gpt-oss-120b"          # blind Q-C judge (different family)

AGENT_TEMPERATURE = 0.3
AGENT_MAX_TOKENS = 512
ROUTER_TEMPERATURE = 0.0
CUSTOMER_TEMPERATURE = 0.7
JUDGE_TEMPERATURE = 0.0

# ---------------------------------------------------------------------------
# Experiment matrix (PLAN.md §2 D6)
# ---------------------------------------------------------------------------
# 2 (down from planned 3): Groq free-tier daily budgets make 3 runs a >2-week affair;
# 2 runs still give a paired repetition per scenario. Raise on Dev Tier.
RUNS_PER_SCENARIO = 2
MAX_CUSTOMER_TURNS = 12          # hard stop per conversation
REQUEST_TIMEOUT_S = 60
RETRY_MAX_ATTEMPTS = 5           # exponential backoff for Groq rate limits
RETRY_BASE_DELAY_S = 2.0

# ---------------------------------------------------------------------------
# Simulated "today" — ALL seeded dates and window math anchor to this, so the
# experiment is reproducible regardless of when it is actually run.
# ---------------------------------------------------------------------------
REFERENCE_DATE = date(2026, 7, 4)

# ---------------------------------------------------------------------------
# Loomora business policy constants (ground truth; mirrored in Checklist.md).
# Prompts/graph are authored from these values — change here, re-author there.
# ---------------------------------------------------------------------------
RETURN_WINDOW_DAYS = {"Basic": 30, "Silver": 30, "Gold": 40}
RETURN_LABEL_FEE_UNDER = 50.00   # orders under this pay the label fee for refunds
RETURN_LABEL_FEE = 4.99          # store-credit returns are always free
REFUND_PROCESSING_DAYS = "5-10 business days"
PRICE_ADJUST_WINDOW_DAYS = 7     # one adjustment per order, issued as store credit
LOST_PARCEL_WAIT_HOURS = 48      # after 'delivered' scan before investigation opens
HUMAN_SUPPORT_HOURS = "9am-6pm ET, Mon-Fri (outside hours: callback ticket)"
