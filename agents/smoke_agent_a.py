"""M3 acceptance: scripted smoke conversations for Agent A across all verticals.

Run:  .venv/Scripts/python agents/smoke_agent_a.py [smoke_id ...]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.agent_a import AgentA  # noqa: E402
from agents.smoke_common import run_suite  # noqa: E402

if __name__ == "__main__":
    run_suite(lambda: AgentA(), "agent_a", sys.argv[1:])
