"""Agent B — the graph-directed agent (PLAN.md §8.3).

Architecture per turn:
  1. GraphSession.route() — one cheap router call (billed to B, purpose='router').
  2. The current node's packet is appended to the CRISP system prompt for THIS TURN ONLY —
     packets are never accumulated into the chained history. That is the token-saving
     mechanism under test: B's fixed overhead is O(one node), not O(the whole manual).
  3. Same tool loop, same tools, same model as Agent A.

One AgentB instance = one conversation (the graph session is stateful). Create a fresh
instance per conversation.
"""

from __future__ import annotations

import time

import config
from agents.base import ToolLoopAgent, TurnMetrics
from graph.engine import Graph, GraphSession

PROMPT_PATH = config.PROMPTS_DIR / "agent_b_system.md"


class AgentB(ToolLoopAgent):
    name = "agent_b"

    def __init__(self, graph: Graph | None = None):
        super().__init__(PROMPT_PATH.read_text(encoding="utf-8"), model=config.AGENT_MODEL)
        self.session = GraphSession(graph or Graph.load())
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

        route = self.session.route(user_msg, last_agent_msg)
        self._packet = self.session.packet()

        reply, metrics = super().respond(history)
        metrics.api_calls.insert(0, route.record)          # router cost billed to B
        metrics.latency_ms = (time.perf_counter() - t0) * 1000  # includes routing time
        metrics.extra = {
            "node": route.node.id,
            "router_reply": route.raw_reply,
            "router_fallback": route.fallback_used,
            "path": list(self.session.path),
        }
        return reply, metrics
