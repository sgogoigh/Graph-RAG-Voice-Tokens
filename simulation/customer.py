"""LLM customer simulator (PLAN.md §10).

Plays the customer from a scenario script + persona. Identical scripts drive both
agents (the opening message is scripted verbatim; later turns are simulated), so A/B
transcripts stay comparable. Ends the conversation with sentinel tokens:
  <<END_SATISFIED>>   goal met or outcome accepted
  <<END_FRUSTRATED>>  giving up unhappy

Customer tokens are recorded for completeness but billed to NEITHER agent.
"""

from __future__ import annotations

import json

import config
from agents.groq_client import CallRecord, chat

PERSONAS = json.loads((config.ROOT / "simulation" / "personas.json").read_text(encoding="utf-8"))

SYSTEM = """\
You are role-playing a CUSTOMER contacting Loomora (an online clothing store) support chat. \
Stay in character at all times.

Who you are: {name}. {email_line}
Why you contacted support: {goal}
Your temperament: {persona}
Scenario behavior: {behavior}

Rules:
- Write ONLY the customer's next chat message: plain text, 1-3 short sentences, no meta \
commentary, no stage directions, never mention being an AI or a test.
- Don't volunteer every detail at once; answer what the agent asks.
- If your goal is fully handled or you accept the final outcome, reply with exactly \
<<END_SATISFIED>> and nothing else.
- If you are giving up unhappy, reply with exactly <<END_FRUSTRATED>> and nothing else.
- Do not end the conversation before the agent has actually addressed (or clearly \
refused) your request."""


class CustomerSim:
    def __init__(self, scenario: dict):
        self.scenario = scenario
        email = scenario["customer"].get("email") or ""
        self.system = SYSTEM.format(
            name=scenario["customer"]["name"],
            email_line=f"Your account email: {email}." if email else "You are browsing as a guest (no account email).",
            goal=scenario["goal"],
            persona=PERSONAS[scenario["persona"]],
            behavior=scenario["behavior"],
        )

    def opening(self) -> str:
        return self.scenario["opening"]

    def reply(self, history: list[dict]) -> tuple[str, CallRecord]:
        """history: the conversation in AGENT perspective (user=customer, assistant=agent).
        Flip roles so the simulator speaks as 'assistant' continuing its own persona."""
        flipped = [
            {"role": "assistant" if m["role"] == "user" else "user", "content": m["content"]}
            for m in history
        ]
        result = chat(
            config.CUSTOMER_MODEL,
            [{"role": "system", "content": self.system}, *flipped],
            temperature=config.CUSTOMER_TEMPERATURE,
            max_tokens=120,
            purpose="customer",
        )
        return (result.message.content or "").strip(), result.record


def end_reason(customer_msg: str) -> str | None:
    if "<<END_SATISFIED>>" in customer_msg:
        return "satisfied"
    if "<<END_FRUSTRATED>>" in customer_msg:
        return "frustrated"
    return None
