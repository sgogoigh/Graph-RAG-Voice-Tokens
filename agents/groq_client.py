"""Shared Groq client with retry/backoff and per-call usage accounting.

Every API call in the experiment (agents, router, customer, judge) goes through
`chat()` so that token usage and latency are captured uniformly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from groq import Groq, APIConnectionError, APIStatusError, RateLimitError

import config

_client: Groq | None = None


def client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=config.GROQ_API_KEY, timeout=config.REQUEST_TIMEOUT_S)
    return _client


@dataclass
class CallRecord:
    """One API call's accounting — the atom of the experiment's metrics."""

    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    purpose: str = "generation"  # generation | router | customer | judge

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ChatResult:
    message: Any                      # the assistant message object (may carry tool_calls)
    record: CallRecord
    raw: Any = field(repr=False, default=None)


def chat(
    model: str,
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 512,
    purpose: str = "generation",
) -> ChatResult:
    """One chat completion with exponential backoff on rate limits / transient errors.

    Groq's llama models occasionally emit malformed tool-call syntax, surfaced as a 400
    with code 'tool_use_failed'. That is model stochasticity, not a bad request: we retry,
    and on the final attempt drop `tools` so the turn degrades to a plain-text answer
    instead of killing the conversation.
    """
    last_err: Exception | None = None
    for attempt in range(config.RETRY_MAX_ATTEMPTS):
        t0 = time.perf_counter()
        last_attempt = attempt == config.RETRY_MAX_ATTEMPTS - 1
        try:
            kwargs: dict[str, Any] = dict(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if tools and not (last_attempt and _is_tool_use_failure(last_err)):
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            resp = client().chat.completions.create(**kwargs)
            latency_ms = (time.perf_counter() - t0) * 1000
            u = resp.usage
            return ChatResult(
                message=resp.choices[0].message,
                record=CallRecord(
                    model=model,
                    latency_ms=latency_ms,
                    prompt_tokens=u.prompt_tokens,
                    completion_tokens=u.completion_tokens,
                    purpose=purpose,
                ),
                raw=resp,
            )
        except RateLimitError as e:
            # A daily-budget (TPD) 429 replenishes in ~an hour — backoff is pointless.
            if "per day" in str(e) or "TPD" in str(e):
                raise RuntimeError(
                    f"Groq DAILY token budget exhausted for {model}. "
                    "Wait for the window to roll or upgrade the tier; see error above."
                ) from e
            last_err = e
            time.sleep(config.RETRY_BASE_DELAY_S * (2**attempt))
        except APIConnectionError as e:
            last_err = e
            time.sleep(config.RETRY_BASE_DELAY_S * (2**attempt))
        except APIStatusError as e:
            if e.status_code in (500, 502, 503) or _is_tool_use_failure(e):
                last_err = e
                time.sleep(config.RETRY_BASE_DELAY_S * (2**attempt))
            else:
                raise
    raise RuntimeError(f"Groq call failed after {config.RETRY_MAX_ATTEMPTS} attempts") from last_err


def _is_tool_use_failure(err: Exception | None) -> bool:
    return isinstance(err, APIStatusError) and err.status_code == 400 and "tool_use_failed" in str(err)
