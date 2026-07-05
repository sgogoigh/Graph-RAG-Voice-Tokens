"""Agent B-spec — Agent B with SPECULATIVE ROUTING (latency experiment).

Motivation: B's ~0.5s/turn latency penalty vs A is the serial router call. Matrix data
shows 62% of turns (>=2) stay on the current node, so we can generate speculatively
with the CURRENT node's packet in parallel with routing:
  - router says "stay"  -> the reply is already generating; router latency vanishes.
  - router says "jump"  -> discard the speculative reply, regenerate with the new
    packet (today's serial cost), and BILL the wasted generation tokens honestly.

Safety guard: speculate only when the current node's tools are all READ-ONLY — a
discarded speculative turn that called get_order cost tokens; one that called
create_ticket would have left a duplicate side effect. Write-capable nodes and the
first turn route serially, exactly like stock Agent B.

The trade being measured: latency saved = stay_rate x router_latency (on speculated
turns) vs tokens wasted = jump_rate x speculative-generation cost.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

import config
from agents.agent_b import AgentB
from agents.base import ToolLoopAgent, TurnMetrics
from graph.engine import Graph

WRITE_TOOLS = {"create_ticket", "initiate_return", "cancel_order", "update_address"}


class AgentBSpeculative(AgentB):
    name = "agent_b_spec"

    def _safe_to_speculate(self, history: list[dict]) -> bool:
        if len(history) < 3:  # first customer turn: routing almost always jumps
            return False
        node = self.session.graph.nodes[self.session.current_id]
        return not (set(node.tools) & WRITE_TOOLS)

    def respond(self, history: list[dict]) -> tuple[str, TurnMetrics]:
        if not self._safe_to_speculate(history):
            reply, m = super().respond(history)
            m.extra["speculated"] = False
            return reply, m

        t0 = time.perf_counter()
        user_msg = history[-1]["content"]
        last_agent_msg = next(
            (m["content"] for m in reversed(history[:-1]) if m["role"] == "assistant"), None
        )

        old_node = self.session.current_id
        self._packet = self.session.packet()  # current node's packet, pre-routing

        with ThreadPoolExecutor(max_workers=1) as ex:
            fut_gen = ex.submit(ToolLoopAgent.respond, self, history)  # speculative gen
            route = self.session.route(user_msg, last_agent_msg)        # router, in parallel
            reply, m = fut_gen.result()

        if route.node.id == old_node:  # HIT: the speculative reply is the real reply
            m.api_calls.insert(0, route.record)
            m.latency_ms = (time.perf_counter() - t0) * 1000
            m.extra = {"node": route.node.id, "router_reply": route.raw_reply,
                       "router_fallback": route.fallback_used, "path": list(self.session.path),
                       "speculated": True, "spec_hit": True}
            return reply, m

        # MISS: discard the reply, keep the bill; regenerate under the routed node.
        wasted = m
        self._packet = self.session.packet()
        reply2, m2 = ToolLoopAgent.respond(self, history)
        m2.api_calls = [route.record] + wasted.api_calls + m2.api_calls
        m2.latency_ms = (time.perf_counter() - t0) * 1000
        m2.extra = {"node": route.node.id, "router_reply": route.raw_reply,
                    "router_fallback": route.fallback_used, "path": list(self.session.path),
                    "speculated": True, "spec_hit": False,
                    "spec_wasted_tokens": sum(c.total_tokens for c in wasted.api_calls),
                    "spec_wasted_tools": json.dumps([tc["name"] for tc in wasted.tool_calls])}
        return reply2, m2


if __name__ == "__main__":
    # tiny wiring check
    import sys
    sys.path.insert(0, str(config.ROOT))
    a = AgentBSpeculative(Graph.load())
    print("wired:", a.name, "entry:", a.session.current_id)
