"""Agent A — the monolithic-prompt baseline (PLAN.md §6).

The entire Loomora operations manual travels in the system prompt on every turn.
No retrieval, no routing: architecture = big prompt + chained history + tools.
"""

from __future__ import annotations

import config
from agents.base import ToolLoopAgent

PROMPT_PATH = config.PROMPTS_DIR / "agent_a_system.md"


class AgentA(ToolLoopAgent):
    name = "agent_a"

    def __init__(self):
        super().__init__(PROMPT_PATH.read_text(encoding="utf-8"), model=config.AGENT_MODEL)
