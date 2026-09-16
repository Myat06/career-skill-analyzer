"""Ollama embedding adapter with resilience: batching, retry/backoff, bounded
concurrency, and a circuit breaker -- the specific gaps rag-pipeline-review.pdf
flagged in the sibling knowledge-base project (a single `raise_for_status()`
with no retry, one HTTP call per source regardless of size, fully serial
ingestion). Provider SDK types never leak past this module.

Transport: this used to POST to Ollama's /api/embed directly via httpx; it now
goes through langchain-ollama's OllamaEmbeddings. OllamaEmbeddings itself has
no batching/retry/backoff/circuit-breaker of its own -- this resilience layer
is bespoke to this project and is kept exactly as it was, just wrapping the
new transport's aembed_documents() call instead of a raw httpx POST.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx
import numpy as np
import ollama
from langchain_ollama import OllamaEmbeddings

from app.config import settings

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 32  # bounds a single Ollama HTTP call to a manageable payload
EMBED_MAX_RETRIES = 3
EMBED_BACKOFF_BASE_SECONDS = 0.5  # exponential: 0.5s, 1s, 2s
EMBED_CONCURRENCY = 4  # bounded parallel batches -- not fully serial, not unbounded
CIRCUIT_FAILURE_THRESHOLD = 5  # consecutive failures before short-circuiting
CIRCUIT_COOLDOWN_SECONDS = 30.0

# Same translated-exception set as app/llm/chat.py -- verified against the
# installed ollama package's _client.py: httpx.HTTPStatusError ->
# ollama.ResponseError, httpx.ConnectError -> builtin ConnectionError, anything
# else (timeouts, etc.) propagates as a raw httpx.HTTPError subtype.
_RETRYABLE_EXCEPTIONS = (ollama.ResponseError, ConnectionError, httpx.HTTPError)


class EmbeddingServiceUnavailable(RuntimeError):
    pass


@dataclass
class _CircuitBreaker:
    consecutive_failures: int = 0
    opened_at: float | None = None

    def before_call(self) -> None:
        if self.opened_at is None:
            return
        if time.monotonic() - self.opened_at < CIRCUIT_COOLDOWN_SECONDS:
            raise EmbeddingServiceUnavailable(
                f"embedding circuit open after {self.consecutive_failures} consecutive "
                f"failures; cooling down for {CIRCUIT_COOLDOWN_SECONDS}s"
            )
        self.opened_at = None  # cooldown elapsed: allow a trial call

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD:
            self.opened_at = time.monotonic()


_circuit = _CircuitBreaker()
_semaphore = asyncio.Semaphore(EMBED_CONCURRENCY)
# Same diagnostic purpose as app/llm/chat.py's _in_flight (a separate counter,
# not shared with it): Ollama serializes inference on this machine regardless
# of EMBED_CONCURRENCY, so a slow batch's log line can show how many other
# embedding batches were in flight at the same time, distinguishing "Ollama is
# slow" from "this batch was queued behind others."
_in_flight = 0

_embed_model = OllamaEmbeddings(
    model=settings.embedding_model,
    base_url=settings.ollama_host,
    client_kwargs={"timeout": 120},
)


def _chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


async def _embed_batch(batch: list[str]) -> list[list[float]]:
    _circuit.before_call()
    last_error: Exception | None = None
    global _in_flight
    for attempt in range(EMBED_MAX_RETRIES):
        _in_flight += 1
        started = time.monotonic()
        try:
            result = await _embed_model.aembed_documents(batch)
            _circuit.record_success()
            logger.info(
                "embed batch ok: size=%d wall=%.2fs in_flight=%d",
                len(batch),
                time.monotonic() - started,
                _in_flight,
            )
            return result
        except _RETRYABLE_EXCEPTIONS as exc:
            last_error = exc
            _circuit.record_failure()
            logger.warning(
                "embed batch failed after %.2fs (size=%d, in_flight=%d), attempt %d/%d: %s",
                time.monotonic() - started,
                len(batch),
                _in_flight,
                attempt + 1,
                EMBED_MAX_RETRIES,
                exc,
            )
            if attempt < EMBED_MAX_RETRIES - 1:
                await asyncio.sleep(EMBED_BACKOFF_BASE_SECONDS * (2**attempt))
        finally:
            _in_flight -= 1
    raise EmbeddingServiceUnavailable(
        f"embedding call failed after {EMBED_MAX_RETRIES} attempts: {last_error}"
    ) from last_error


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Order-preserving: batches are built as sequential slices and awaited via
    gather, which resolves in submission order regardless of completion order.
    """
    if not texts:
        return []

    async def _bounded(batch: list[str]) -> list[list[float]]:
        async with _semaphore:
            return await _embed_batch(batch)

    batches = list(_chunks(texts, EMBED_BATCH_SIZE))
    results = await asyncio.gather(*(_bounded(b) for b in batches))

    embeddings: list[list[float]] = []
    for batch_result in results:
        embeddings.extend(batch_result)
    return embeddings


async def embed_query(text: str) -> list[float]:
    embeddings = await embed_texts([text])
    return embeddings[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Shared by every embedding-comparison scorer (resume keyword alignment,
    skill-gap unit coverage) -- was independently reimplemented in both, byte
    for byte identical, before being consolidated here."""
    va, vb = np.array(a), np.array(b)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom else 0.0
