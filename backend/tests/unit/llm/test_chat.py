"""Tests app.llm.chat's options pass-through and retry/failure behavior.

Temperature: omitted by default (every existing caller -- narrative.py,
resume_score.py, consultation_chat.py -- keeps the model's own default
sampling), included only when a caller explicitly asks for it
(text_evidence.py pins temperature=0 for its factual yes/no matching task --
see its module docstring for why).

Mocking target: ChatOllama's `ainvoke` method, patched on the class (not the
`_llm` instance) -- this is the real boundary between our adapter code and
the LangChain/Ollama SDK post-migration (the old version of this file mocked
httpx.AsyncClient.post directly, which no longer applies now that ChatOllama
sits underneath instead of a raw httpx call). Patched on the class because
ChatOllama is a pydantic BaseModel with `extra="ignore"`, which rejects
setting arbitrary attributes directly on an instance.
"""

from types import SimpleNamespace

import httpx
import ollama
import pytest

import app.llm.chat as chat_module
from app.llm.chat import ChatServiceUnavailable, chat


def _patch_ainvoke(monkeypatch, fake):
    monkeypatch.setattr(type(chat_module._llm), "ainvoke", fake)


@pytest.mark.asyncio
async def test_temperature_omitted_by_default(monkeypatch):
    seen_options = {}

    async def fake_ainvoke(self, messages, options=None, **kwargs):
        seen_options.update(options or {})
        return SimpleNamespace(content="ok")

    _patch_ainvoke(monkeypatch, fake_ainvoke)

    await chat([{"role": "user", "content": "hi"}])
    assert "temperature" not in seen_options


@pytest.mark.asyncio
async def test_explicit_temperature_is_sent(monkeypatch):
    seen_options = {}

    async def fake_ainvoke(self, messages, options=None, **kwargs):
        seen_options.update(options or {})
        return SimpleNamespace(content="ok")

    _patch_ainvoke(monkeypatch, fake_ainvoke)

    await chat([{"role": "user", "content": "hi"}], temperature=0.0)
    assert seen_options["temperature"] == 0.0


@pytest.mark.asyncio
async def test_num_ctx_still_present_alongside_an_explicit_temperature(monkeypatch):
    seen_options = {}

    async def fake_ainvoke(self, messages, options=None, **kwargs):
        seen_options.update(options or {})
        return SimpleNamespace(content="ok")

    _patch_ainvoke(monkeypatch, fake_ainvoke)

    await chat([{"role": "user", "content": "hi"}], temperature=0.0)
    assert seen_options["num_ctx"] == chat_module.CHAT_NUM_CTX


@pytest.mark.asyncio
async def test_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def flaky_ainvoke(self, messages, options=None, **kwargs):
        calls["n"] += 1
        if calls["n"] < chat_module.CHAT_MAX_RETRIES:
            raise ollama.ResponseError("transient failure", 500)
        return SimpleNamespace(content="ok")

    _patch_ainvoke(monkeypatch, flaky_ainvoke)

    result = await chat([{"role": "user", "content": "hi"}])
    assert result == "ok"
    assert calls["n"] == chat_module.CHAT_MAX_RETRIES


@pytest.mark.asyncio
async def test_raises_chat_service_unavailable_after_exhausting_retries(monkeypatch):
    async def always_fail(self, messages, options=None, **kwargs):
        raise ConnectionError("Failed to connect to Ollama")

    _patch_ainvoke(monkeypatch, always_fail)

    with pytest.raises(ChatServiceUnavailable):
        await chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_httpx_error_is_also_retryable(monkeypatch):
    async def always_timeout(self, messages, options=None, **kwargs):
        raise httpx.ReadTimeout("timed out")

    _patch_ainvoke(monkeypatch, always_timeout)

    with pytest.raises(ChatServiceUnavailable):
        await chat([{"role": "user", "content": "hi"}])
