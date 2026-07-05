"""Latency experiment: same smoke suite through speculative-routing Agent B."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.agent_b_spec import AgentBSpeculative  # noqa: E402
from agents.smoke_common import run_suite  # noqa: E402
from graph.engine import Graph  # noqa: E402

if __name__ == "__main__":
    graph = Graph.load()
    run_suite(lambda: AgentBSpeculative(graph), "agent_b_spec", sys.argv[1:])
