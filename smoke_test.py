"""M0 acceptance test: one successful Groq API call per model tier using .env key.

Run:  .venv/Scripts/python smoke_test.py
"""

import sys
import time

from groq import Groq

import config


def main() -> int:
    if not config.GROQ_API_KEY:
        print("FAIL: GROQ_API_KEY not found in .env")
        return 1

    client = Groq(api_key=config.GROQ_API_KEY)
    models = {
        "agent": config.AGENT_MODEL,
        "router/customer": config.ROUTER_MODEL,
        "judge": config.JUDGE_MODEL,
    }

    ok = True
    for role, model in models.items():
        t0 = time.perf_counter()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=8,
                temperature=0,
            )
            ms = (time.perf_counter() - t0) * 1000
            u = resp.usage
            print(
                f"PASS  {role:<16} {model:<28} {ms:7.0f} ms  "
                f"tokens: {u.prompt_tokens}p + {u.completion_tokens}c  "
                f"-> {resp.choices[0].message.content!r}"
            )
        except Exception as e:  # noqa: BLE001 - report and continue
            print(f"FAIL  {role:<16} {model:<28} {type(e).__name__}: {e}")
            ok = False

    print("\nSmoke test:", "ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
