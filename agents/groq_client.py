"""Shared multi-provider LLM client with retry/backoff and per-call usage accounting.

Every API call in the experiment (agents, router, customer, judge) goes through
`chat()` so that token usage and latency are captured uniformly.

Providers are selected by model-string prefix:
  "gemini/<model>"   -> Google Gemini via its OpenAI-compatible endpoint
  "mistral/<model>"  -> Mistral La Plateforme (OpenAI-compatible)
  anything else      -> Groq

Both providers speak the OpenAI chat-completions shape (messages, tools, usage,
tool_calls), so the rest of the codebase never branches on provider.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import openai
from groq import Groq, APIConnectionError, APIStatusError, RateLimitError

import config

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"

_client: Groq | None = None
_gemini: openai.OpenAI | None = None
_mistral: openai.OpenAI | None = None

# provider-agnostic exception groups (groq and openai SDKs mirror each other's types)
RATE_LIMIT_ERRORS = (RateLimitError, openai.RateLimitError)
CONNECTION_ERRORS = (APIConnectionError, openai.APIConnectionError)
STATUS_ERRORS = (APIStatusError, openai.APIStatusError)


def client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=config.GROQ_API_KEY, timeout=config.REQUEST_TIMEOUT_S)
    return _client


def gemini_client() -> openai.OpenAI:
    global _gemini
    if _gemini is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY missing from .env")
        _gemini = openai.OpenAI(api_key=config.GEMINI_API_KEY, base_url=GEMINI_BASE_URL,
                                timeout=config.REQUEST_TIMEOUT_S)
    return _gemini


def mistral_client() -> openai.OpenAI:
    global _mistral
    if _mistral is None:
        if not config.MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY missing from .env")
        _mistral = openai.OpenAI(api_key=config.MISTRAL_API_KEY, base_url=MISTRAL_BASE_URL,
                                 timeout=config.REQUEST_TIMEOUT_S)
    return _mistral


def _create(model: str, kwargs: dict) -> Any:
    if model.startswith("gemini/"):
        return gemini_client().chat.completions.create(model=model.split("/", 1)[1], **kwargs)
    if model.startswith("mistral/"):
        return mistral_client().chat.completions.create(model=model.split("/", 1)[1], **kwargs)
    return client().chat.completions.create(model=model, **kwargs)


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
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if tools and not (last_attempt and _is_tool_use_failure(last_err)):
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"
            resp = _create(model, kwargs)
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
        except RATE_LIMIT_ERRORS as e:
            # A daily-budget 429 replenishes in ~an hour+ — backoff is pointless.
            # Groq phrases it "per day (TPD/RPD)"; Gemini quota ids say "...PerDay...".
            if _is_daily_limit(e):
                raise RuntimeError(
                    f"DAILY budget exhausted for {model}. "
                    "Wait for the window to roll or upgrade the tier; see error above."
                ) from e
            last_err = e
            time.sleep(config.RETRY_BASE_DELAY_S * (2**attempt))
        except CONNECTION_ERRORS as e:
            last_err = e
            time.sleep(config.RETRY_BASE_DELAY_S * (2**attempt))
        except STATUS_ERRORS as e:
            if e.status_code in (500, 502, 503) or _is_tool_use_failure(e):
                last_err = e
                time.sleep(config.RETRY_BASE_DELAY_S * (2**attempt))
            else:
                raise
    raise RuntimeError(f"LLM call failed after {config.RETRY_MAX_ATTEMPTS} attempts") from last_err


def _is_daily_limit(err: Exception) -> bool:
    s = str(err).lower().replace(" ", "").replace("_", "")
    return "perday" in s or "tpd" in s or "rpd" in s


def _is_tool_use_failure(err: Exception | None) -> bool:
    return (isinstance(err, STATUS_ERRORS) and getattr(err, "status_code", None) == 400
            and "tool_use_failed" in str(err))
