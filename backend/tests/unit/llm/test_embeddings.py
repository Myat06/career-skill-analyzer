"""Tests the resilience behavior of app/llm/embeddings.py: retry/backoff on
transient failure, and the circuit breaker opening after repeated failures --
the exact gaps rag-pipeline-review.pdf flagged as missing in the sibling
knowledge-base project. This resilience layer is bespoke to this project (not
provided by OllamaEmbeddings) and is preserved unchanged across the
LangChain migration.

Mocking target: OllamaEmbeddings' `aembed_documents` method, patched on the
class (not the `_embed_model` instance) -- the real boundary between our
adapter code and the LangChain/Ollama SDK post-migration (the old version of
this file mocked httpx.AsyncClient.post directly, which no longer applies).
Patched on the class because OllamaEmbeddings is a pydantic BaseModel with
`extra="ignore"`, which rejects setting arbitrary attributes directly on an
instance.
"""

import ollama
import pytest

import app.llm.embeddings as embeddings_module
from app.llm.embeddings import EmbeddingServiceUnavailable, embed_texts


def _patch_aembed_documents(monkeypatch, fake):
    monkeypatch.setattr(type(embeddings_module._embed_model), "aembed_documents", fake)


@pytest.fixture(autouse=True)
def reset_circuit_and_speed_up_backoff(monkeypatch):
    embeddings_module._circuit.consecutive_failures = 0
    embeddings_module._circuit.opened_at = None
    monkeypatch.setattr(embeddings_module, "EMBED_BACKOFF_BASE_SECONDS", 0.001)


@pytest.mark.asyncio
async def test_embed_texts_empty_input_short_circuits():
    assert await embed_texts([]) == []


@pytest.mark.asyncio
async def test_embed_texts_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def fake_aembed_documents(self, texts):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ollama.ResponseError("transient failure", 500)
        return [[0.1, 0.2]] * len(texts)

    _patch_aembed_documents(monkeypatch, fake_aembed_documents)

    result = await embed_texts(["hello"])
    assert result == [[0.1, 0.2]]
    assert calls["n"] == 3  # two failures, then a success within EMBED_MAX_RETRIES


@pytest.mark.asyncio
async def test_embed_texts_raises_after_exhausting_retries(monkeypatch):
    async def always_fail(self, texts):
        raise ollama.ResponseError("server error", 500)

    _patch_aembed_documents(monkeypatch, always_fail)

    with pytest.raises(EmbeddingServiceUnavailable):
        await embed_texts(["hello"])


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_repeated_failures(monkeypatch):
    async def always_fail(self, texts):
        raise ollama.ResponseError("server error", 500)

    _patch_aembed_documents(monkeypatch, always_fail)

    # each embed_texts call exhausts EMBED_MAX_RETRIES failures; enough calls
    # should push consecutive_failures past CIRCUIT_FAILURE_THRESHOLD
    for _ in range(3):
        with pytest.raises(EmbeddingServiceUnavailable):
            await embed_texts(["hello"])

    assert embeddings_module._circuit.opened_at is not None

    with pytest.raises(EmbeddingServiceUnavailable, match="circuit open"):
        await embed_texts(["hello"])


@pytest.mark.asyncio
async def test_batches_split_across_multiple_calls(monkeypatch):
    monkeypatch.setattr(embeddings_module, "EMBED_BATCH_SIZE", 2)
    calls = []

    async def fake_aembed_documents(self, texts):
        calls.append(list(texts))
        return [[float(len(t))] for t in texts]

    _patch_aembed_documents(monkeypatch, fake_aembed_documents)

    texts = ["a", "bb", "ccc", "dddd", "e"]
    result = await embed_texts(texts)

    assert len(calls) == 3  # ceil(5/2)
    assert result == [[1.0], [2.0], [3.0], [4.0], [1.0]]  # order preserved across batches
