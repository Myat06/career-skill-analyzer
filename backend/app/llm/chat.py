"""LangChain/Ollama-backed chat adapter, shared by scoring/narrative.py and
scoring/resume_score.py's presentation grading. Failures raise
ChatServiceUnavailable so callers can degrade gracefully (see
SkillGapResponse.narrative_status) instead of failing the whole request --
deterministic scoring never depends on the chat model being reachable.

Transport: this used to POST to Ollama's /api/chat directly via httpx; it now
goes through langchain-ollama's ChatOllama. `options` is still built by hand on
every call rather than left to ChatOllama's constructor-field defaults --
verified against the installed langchain-ollama source (chat_models.py
_chat_params): passing `options=` as a call-time kwarg *replaces* rather than
merges with whatever the constructor's own fields (num_ctx, temperature, ...)
would have produced, so num_ctx must be included here on every call too, not
just set once on the constructor. `reasoning` (Ollama's `think` field) *is*
correctly read from the constructor when not passed per call, so it's set
once below and never needs per-call handling.
"""

import json
import logging
import re
import time

import httpx
import ollama
from langchain_ollama import ChatOllama

from app.config import settings

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

CHAT_TIMEOUT_SECONDS = 120
CHAT_MAX_RETRIES = 2
# Ollama's own default num_ctx (2048) is far below what this model supports and silently
# truncates both the prompt and the response once exceeded -- no error, just a cut-off
# reply -- discovered when resume_score.py's rubric prompt (which embeds a full sample
# resume) got its JSON output truncated mid-object under the default.
CHAT_NUM_CTX = 8192
# qwen3.5 (the current chat_model) has a "thinking" capability Ollama enables by
# default: a chain-of-thought pass returned separately (message.thinking over the
# raw API; ChatOllama surfaces it as additional_kwargs["reasoning_content"] when
# reasoning=True), so it never leaks into message.content or breaks
# extract_json_object() either way -- but the thinking tokens still count against
# CHAT_NUM_CTX like any other output, and a trivial one-line request measured
# ~38x slower with it on (24.5s vs 0.65s). None of this module's callers need
# visible reasoning (rubric grading, narrative JSON, the consultation chat's
# system-prompt-driven replies are all instruction-following, not reasoning
# puzzles), so it's disabled here rather than per call site.
CHAT_THINK = False

# ollama.AsyncClient (which ChatOllama wraps) translates httpx.HTTPStatusError ->
# ollama.ResponseError and httpx.ConnectError -> builtin ConnectionError (verified
# against the installed ollama package's _client.py); anything else (timeouts, other
# connect failures) propagates as a raw httpx.HTTPError subtype.
_RETRYABLE_EXCEPTIONS = (ollama.ResponseError, ConnectionError, httpx.HTTPError)


class ChatServiceUnavailable(RuntimeError):
    pass


# Ollama serializes inference on this machine regardless of how many requests
# the app fires concurrently (single GPU, one loaded model) -- this counter
# exists so a slow call's log line can show how many other chat() calls were
# in flight at the same time, distinguishing "the model is slow" from "this
# call was queued behind others." Plain int, not a lock: asyncio is
# single-threaded/cooperative, so increment/decrement between awaits is safe
# without one.
_in_flight = 0

_llm = ChatOllama(
    model=settings.chat_model,
    base_url=settings.ollama_host,
    reasoning=CHAT_THINK,
    client_kwargs={"timeout": CHAT_TIMEOUT_SECONDS},
)


def _build_options(temperature: float | None) -> dict:
    options = {"num_ctx": CHAT_NUM_CTX}
    if temperature is not None:
        options["temperature"] = temperature
    return options


async def chat(messages: list[dict], temperature: float | None = None) -> str:
    """temperature is omitted from the request (letting Ollama use the
    model's own default, ~0.8 for qwen3.5) unless a caller explicitly passes
    one -- narrative.py/resume_score.py/consultation_chat.py all want that
    default behavior unchanged. text_evidence.py is the one caller that pins
    temperature=0: its task is a factual yes/no judgment (does this quote
    exist and support this element), not open-ended writing, and a live
    check found the default temperature genuinely changing which elements
    got matched between two otherwise-identical calls -- greedy decoding
    removes that source of run-to-run variance for free, no extra call
    needed."""
    options = _build_options(temperature)
    last_error: Exception | None = None
    global _in_flight
    for _attempt in range(CHAT_MAX_RETRIES):
        _in_flight += 1
        started = time.monotonic()
        try:
            response = await _llm.ainvoke(messages, options=options)
            content = response.content
            if not isinstance(content, str):
                raise TypeError(f"expected str content from ChatOllama, got {type(content)}")
            wall_seconds = time.monotonic() - started
            meta = getattr(response, "response_metadata", None) or {}
            # total_duration is Ollama's own server-side measurement (ns) of the
            # whole call, so wall_seconds >> total_duration means time was lost
            # to something outside Ollama's own accounting (network, or this
            # request queued behind another before Ollama started the clock).
            logger.info(
                "chat call ok: wall=%.2fs ollama_total=%.2fs ollama_eval=%.2fs in_flight=%d",
                wall_seconds,
                meta.get("total_duration", 0) / 1e9,
                meta.get("eval_duration", 0) / 1e9,
                _in_flight,
            )
            return content
        except _RETRYABLE_EXCEPTIONS as exc:
            last_error = exc
            logger.warning(
                "chat call failed after %.2fs (in_flight=%d), attempt %d/%d: %s",
                time.monotonic() - started,
                _in_flight,
                _attempt + 1,
                CHAT_MAX_RETRIES,
                exc,
            )
        finally:
            _in_flight -= 1
    raise ChatServiceUnavailable(f"chat call failed after {CHAT_MAX_RETRIES} attempts: {last_error}") from last_error


def extract_json_object(raw: str) -> dict | None:
    """Pulls the first {...} object out of a chat reply and parses it -- models
    routinely wrap JSON in prose or a markdown code fence despite being told not
    to. Shared by every module that asks the model for structured JSON output
    (narrative.py, resume_score.py, narrative_prompts.py); was independently
    reimplemented, identically, in all three before being consolidated here."""
    match = _JSON_OBJECT_RE.search(raw)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
