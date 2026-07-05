"""Smoke test: one successful call per configured model tier (Groq and/or Gemini),
plus a tool-calling check on the agent model (the agents depend on function calling).

Run:  .venv/Scripts/python smoke_test.py
"""

import sys

from agents.groq_client import chat

import config

PING_TOOL = [{
    "type": "function",
    "function": {
        "name": "ping",
        "description": "Echo a value back. Call this with value='pong'.",
        "parameters": {"type": "object",
                       "properties": {"value": {"type": "string"}},
                       "required": ["value"]},
    },
}]


def main() -> int:
    models = {
        "agent": config.AGENT_MODEL,
        "router/customer": config.ROUTER_MODEL,
        "judge": config.JUDGE_MODEL,
    }

    ok = True
    for role, model in models.items():
        try:
            r = chat(model, [{"role": "user", "content": "Reply with exactly: OK"}],
                     temperature=0, max_tokens=64, purpose="smoke")
            rec = r.record
            print(f"PASS  {role:<16} {model:<32} {rec.latency_ms:7.0f} ms  "
                  f"tokens: {rec.prompt_tokens}p + {rec.completion_tokens}c  "
                  f"-> {(r.message.content or '')[:20]!r}")
        except Exception as e:  # noqa: BLE001 - report and continue
            print(f"FAIL  {role:<16} {model:<32} {type(e).__name__}: {str(e)[:140]}")
            ok = False

    # tool-calling check on the agent model
    try:
        r = chat(config.AGENT_MODEL,
                 [{"role": "user", "content": "Call the ping tool with value='pong'."}],
                 tools=PING_TOOL, temperature=0, max_tokens=64, purpose="smoke")
        tcs = r.message.tool_calls or []
        called = tcs and tcs[0].function.name == "ping"
        print(f"{'PASS' if called else 'FAIL'}  {'agent tool-call':<16} "
              f"{config.AGENT_MODEL:<32} tool_calls={[(t.function.name, t.function.arguments) for t in tcs]}")
        ok = ok and bool(called)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  agent tool-call  {type(e).__name__}: {str(e)[:140]}")
        ok = False

    print("\nSmoke test:", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
