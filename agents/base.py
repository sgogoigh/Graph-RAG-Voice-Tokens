"""Generic tool-loop support agent. Agent A uses it as-is with the monolithic prompt;
Agent B (M5) subclasses/extends it by injecting a per-turn graph node packet.

`respond()` takes the visible conversation history (user/assistant messages only)
and returns the reply plus a full accounting of every API call and tool call made
this turn — the raw material for results/metrics/turns.csv.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

import config
from agents import tools
from agents.groq_client import CallRecord, chat

MAX_TOOL_ITERATIONS = 6


@dataclass
class TurnMetrics:
    latency_ms: float = 0.0
    api_calls: list[CallRecord] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)  # {name, arguments, result}

    @property
    def prompt_tokens(self) -> int:
        return sum(c.prompt_tokens for c in self.api_calls)

    @property
    def completion_tokens(self) -> int:
        return sum(c.completion_tokens for c in self.api_calls)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ToolLoopAgent:
    name = "agent"

    def __init__(self, system_prompt: str, model: str = config.AGENT_MODEL):
        self.system_prompt = system_prompt
        self.model = model

    # Agent B overrides this to append the graph node packet for the current turn.
    def build_messages(self, history: list[dict]) -> list[dict]:
        return [{"role": "system", "content": self.system_prompt}, *history]

    def respond(self, history: list[dict]) -> tuple[str, TurnMetrics]:
        """history: alternating {'role': 'user'|'assistant', 'content': str} messages,
        ending with the latest user message. Returns (reply_text, metrics)."""
        metrics = TurnMetrics()
        messages = self.build_messages(history)
        t0 = time.perf_counter()

        for _ in range(MAX_TOOL_ITERATIONS):
            result = chat(
                self.model,
                messages,
                tools=tools.TOOL_SCHEMAS,
                temperature=config.AGENT_TEMPERATURE,
                max_tokens=config.AGENT_MAX_TOKENS,
                purpose="generation",
            )
            metrics.api_calls.append(result.record)
            msg = result.message

            if not msg.tool_calls:
                metrics.latency_ms = (time.perf_counter() - t0) * 1000
                return (msg.content or "").strip(), metrics

            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                out = tools.execute_tool(tc.function.name, tc.function.arguments)
                metrics.tool_calls.append(
                    {"name": tc.function.name, "arguments": tc.function.arguments, "result": out}
                )
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": out})

        # Tool loop exhausted — force a plain-text answer so the conversation can't stall.
        messages.append(
            {"role": "user", "content": "(system: answer the customer now in plain text, without calling more tools)"}
        )
        result = chat(self.model, messages, temperature=config.AGENT_TEMPERATURE,
                      max_tokens=config.AGENT_MAX_TOKENS, purpose="generation")
        metrics.api_calls.append(result.record)
        metrics.latency_ms = (time.perf_counter() - t0) * 1000
        return (result.message.content or "").strip(), metrics


def render_transcript_md(title: str, turns: list[dict]) -> str:
    """turns: [{'role', 'content', 'metrics': TurnMetrics|None}] -> readable markdown."""
    lines = [f"# {title}", ""]
    for t in turns:
        who = "Customer" if t["role"] == "user" else "Agent"
        lines.append(f"**{who}:** {t['content']}")
        m: TurnMetrics | None = t.get("metrics")
        if m:
            tool_names = ", ".join(tc["name"] for tc in m.tool_calls) or "none"
            lines.append(
                f"> turn: {m.latency_ms:.0f} ms | {m.prompt_tokens}p + {m.completion_tokens}c tokens "
                f"| {len(m.api_calls)} API call(s) | tools: {tool_names}"
            )
        lines.append("")
    return "\n".join(lines)


def metrics_row(m: TurnMetrics) -> dict:
    return {
        "latency_ms": round(m.latency_ms, 1),
        "prompt_tokens": m.prompt_tokens,
        "completion_tokens": m.completion_tokens,
        "total_tokens": m.total_tokens,
        "api_calls": len(m.api_calls),
        "tool_calls": json.dumps([tc["name"] for tc in m.tool_calls]),
    }
