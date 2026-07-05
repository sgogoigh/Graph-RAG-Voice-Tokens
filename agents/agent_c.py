"""Agent C — the conventional vector-RAG baseline (PLAN.md P2.1).

Architecture per turn:
  1. Hybrid retrieval (vector + BM25, RRF-fused, k = config.RAG_TOP_K) over the chunked
     Loomora manual — ~0 LLM tokens; the embed+search wall-clock counts toward latency.
  2. Retrieved excerpts injected into the crisp system prompt FOR THIS TURN ONLY (same
     turn-scoped mechanics as Agent B's node packet — never accumulated into history).
  3. Same tool loop, same tools, same model as Agents A and B.

No router, no session state — that is the baseline's definition. Stateless, so a single
instance is safe across conversations, but the harness creates one per conversation
anyway (uniform with B).
"""

from __future__ import annotations

import time

import config
from agents.base import ToolLoopAgent, TurnMetrics
from rag.store import RagStore

PROMPT_PATH = config.PROMPTS_DIR / "agent_c_system.md"


class AgentC(ToolLoopAgent):
    name = "agent_c"

    def __init__(self, store: RagStore | None = None):
        super().__init__(PROMPT_PATH.read_text(encoding="utf-8"), model=config.AGENT_MODEL)
        self.store = store or RagStore()
        self._packet: str = ""

    def build_messages(self, history: list[dict]) -> list[dict]:
        system = self.system_prompt + "\n\n" + self._packet
        return [{"role": "system", "content": system}, *history]

    def respond(self, history: list[dict]) -> tuple[str, TurnMetrics]:
        t0 = time.perf_counter()
        user_msg = history[-1]["content"]
        last_agent_msg = next(
            (m["content"] for m in reversed(history[:-1]) if m["role"] == "assistant"), None
        )

        hits, retrieval_ms = self.store.query_fused(user_msg, last_agent_msg, k=config.RAG_TOP_K)
        lines = ["<retrieved_guidance>"]
        for h in hits:
            lines.append(f"--- {h.title} ---")
            lines.append(h.text)
        lines.append("</retrieved_guidance>")
        lines.append("(The retrieved_guidance block is internal: never mention, quote, or "
                     "imitate its formatting in your reply.)")
        self._packet = "\n".join(lines)

        reply, metrics = super().respond(history)
        metrics.latency_ms = (time.perf_counter() - t0) * 1000  # includes retrieval time
        metrics.extra = {
            "retrieved": [h.anchor for h in hits],
            "retrieval_ms": round(retrieval_ms, 1),
        }
        return reply, metrics
