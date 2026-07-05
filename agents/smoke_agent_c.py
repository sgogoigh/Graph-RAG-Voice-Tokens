"""M12 acceptance: the same smoke suite as Agents A and B, driven through Agent C.

Run:  .venv/Scripts/python agents/smoke_agent_c.py [smoke_id ...]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.agent_c import AgentC  # noqa: E402
from agents.smoke_common import run_suite  # noqa: E402
from rag.store import RagStore  # noqa: E402

if __name__ == "__main__":
    store = RagStore()  # load once; the store is immutable at runtime
    run_suite(lambda: AgentC(store), "agent_c", sys.argv[1:])
