"""M5 acceptance: the same smoke suite as Agent A, driven through Agent B.

Run:  .venv/Scripts/python agents/smoke_agent_b.py [smoke_id ...]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.agent_b import AgentB  # noqa: E402
from agents.smoke_common import run_suite  # noqa: E402
from graph.engine import Graph  # noqa: E402

if __name__ == "__main__":
    graph = Graph.load()  # load once, share the immutable graph across conversations
    run_suite(lambda: AgentB(graph), "agent_b", sys.argv[1:])
