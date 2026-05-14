"""app.llm.client: AsyncOpenAI wrapper + fallback + first-delta timeout."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Callable

import pytest


def _mk_stream(deltas: list[str], tokens: int = 42, raise_mid: Exception | None = None):
    """Build a fake openai streaming response. Each chunk has .choices[0].delta.content."""
    class _FakeChunk:
        def __init__(self, content: str):
            self.choices = [SimpleNamespace(delta=SimpleNamespace(content=content),
                                            finish_reason=None)]
            self.usage = None

    class _FakeFinal:
        def __init__(self, tokens: int):
            self.choices = [SimpleNamespace(delta=SimpleNamespace(content=""),
                                            finish_reason="stop")]
            self.usage = SimpleNamespace(prompt_tokens=tokens // 3,
                                         completion_tokens=tokens - tokens // 3,
                                         total_tokens=tokens)

    async def gen():
        for i, d in enumerate(deltas):
            if raise_mid is not None and i == 1:
                raise raise_mid
            yield _FakeChunk(d)
        yield _FakeFinal(tokens)

    return gen()


class _FakeClient:
    def __init__(self, model_plan: dict[str, Callable[[], object]]):
        self._plan = model_plan
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, *, model, stream, **kwargs):
        assert stream is True
        self.calls.append({"model": model, "stream": stream, **kwargs})
        factory = self._plan.get(model)
        if factory is None:
            raise RuntimeError(f"unexpected model: {model}")
        return factory()


class _FakeOneShotClient:
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, *, model, stream, **kwargs):
        assert stream is False
        self.calls.append({"model": model, **kwargs})
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"ok":true}', reasoning_content=""),
                    finish_reason="stop",
                )
            ]
        )


def _patch_client(monkeypatch, fake: _FakeClient):
    from app.llm import client as c
    monkeypatch.setattr(c, "_client", fake)


def _patch_primary_fallback_models(monkeypatch):
    from app.llm import client as c
    monkeypatch.setattr(c.settings, "llm_model", "deepseek-v4-pro")
    monkeypatch.setattr(c.settings, "llm_fallback_model", "deepseek-v4-flash")


@pytest.mark.asyncio
async def test_chat_stream_happy_primary(monkeypatch):
    from app.llm.client import chat_stream_with_fallback
    from app.llm import client as c
    fake = _FakeClient({c.settings.llm_model: lambda: _mk_stream(["Hello ", "world"], tokens=30)})
    _patch_client(monkeypatch, fake)

    events = []
    async for ev in chat_stream_with_fallback(
        messages=[{"role": "user", "content": "hi"}],
        tier="primary", temperature=0.7, max_tokens=100,
    ):
        events.append(ev)

    types = [e["type"] for e in events]
    assert types == ["model", "delta", "delta", "done"]
    assert events[0]["modelUsed"] == c.settings.llm_model
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "Hello world"
    assert events[-1]["full"] == "Hello world"
    assert events[-1]["tokens_used"] == 30


@pytest.mark.asyncio
async def test_chat_stream_primary_error_falls_back(monkeypatch):
    from app.llm.client import chat_stream_with_fallback
    _patch_primary_fallback_models(monkeypatch)
    # Primary yields one delta then raises mid-stream (at i==1)
    fake = _FakeClient({
        "deepseek-v4-pro": lambda: _mk_stream(["first", "second"], raise_mid=RuntimeError("boom")),
        "deepseek-v4-flash": lambda: _mk_stream(["flash ok"], tokens=15),
    })
    _patch_client(monkeypatch, fake)

    events = []
    async for ev in chat_stream_with_fallback(
        messages=[{"role": "user", "content": "hi"}],
        tier="primary", temperature=0.7, max_tokens=100,
    ):
        events.append(ev)

    types = [e["type"] for e in events]
    assert types.count("model") == 2
    assert events[0]["modelUsed"] == "deepseek-v4-pro"
    second_model = [e for e in events if e["type"] == "model"][1]
    assert second_model["modelUsed"] == "deepseek-v4-flash"
    assert events[-1]["full"] == "flash ok"


@pytest.mark.asyncio
async def test_chat_stream_both_fail_raises_upstream(monkeypatch):
    from app.llm.client import chat_stream_with_fallback
    from app.services.exceptions import UpstreamLLMError
    _patch_primary_fallback_models(monkeypatch)
    fake = _FakeClient({
        "deepseek-v4-pro": lambda: _mk_stream([], raise_mid=RuntimeError("primary down")),
        "deepseek-v4-flash": lambda: _mk_stream([], raise_mid=RuntimeError("fallback down")),
    })
    _patch_client(monkeypatch, fake)

    with pytest.raises(UpstreamLLMError) as exc:
        async for _ in chat_stream_with_fallback(
            messages=[{"role":"u","content":"x"}],
            tier="primary", temperature=0.7, max_tokens=10,
        ):
            pass
    assert exc.value.code == "UPSTREAM_LLM_FAILED"


@pytest.mark.asyncio
async def test_chat_stream_first_delta_timeout_triggers_fallback(monkeypatch):
    from app.llm.client import chat_stream_with_fallback
    _patch_primary_fallback_models(monkeypatch)

    async def _slow_primary():
        await asyncio.sleep(0.1)
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content="too late"),
                                     finish_reason=None)],
            usage=None,
        )

    fake = _FakeClient({
        "deepseek-v4-pro": _slow_primary,
        "deepseek-v4-flash": lambda: _mk_stream(["on time"], tokens=5),
    })
    _patch_client(monkeypatch, fake)

    events = []
    async for ev in chat_stream_with_fallback(
        messages=[{"role":"u","content":"x"}],
        tier="primary", temperature=0.7, max_tokens=10,
        first_delta_timeout_ms=30,
    ):
        events.append(ev)

    assert events[-1]["full"] == "on time"
    models = [e["modelUsed"] for e in events if e["type"] == "model"]
    assert "deepseek-v4-flash" in models


@pytest.mark.asyncio
async def test_chat_stream_empty_primary_triggers_fallback(monkeypatch):
    from app.llm.client import chat_stream_with_fallback
    _patch_primary_fallback_models(monkeypatch)
    fake = _FakeClient({
        "deepseek-v4-pro": lambda: _mk_stream([], tokens=0),
        "deepseek-v4-flash": lambda: _mk_stream(["backup"], tokens=3),
    })
    _patch_client(monkeypatch, fake)

    events = []
    async for ev in chat_stream_with_fallback(
        messages=[{"role":"u","content":"x"}],
        tier="primary", temperature=0.7, max_tokens=10,
    ):
        events.append(ev)

    assert events[-1]["full"] == "backup"


@pytest.mark.asyncio
async def test_chat_stream_tier_fast_uses_fast_model(monkeypatch):
    from app.llm.client import chat_stream_with_fallback
    from app.llm import client as c
    fake = _FakeClient({c.settings.llm_fast_model: lambda: _mk_stream(["fast"], tokens=2)})
    _patch_client(monkeypatch, fake)

    events = []
    async for ev in chat_stream_with_fallback(
        messages=[{"role":"u","content":"x"}],
        tier="fast", temperature=0.9, max_tokens=200,
    ):
        events.append(ev)
    assert events[0]["modelUsed"] == c.settings.llm_fast_model


@pytest.mark.asyncio
async def test_chat_stream_enables_thinking_for_mimo_models(monkeypatch):
    from app.llm.client import chat_stream_with_fallback
    from app.llm import client as c
    fake = _FakeClient({c.settings.llm_model: lambda: _mk_stream(["ok"], tokens=2)})
    _patch_client(monkeypatch, fake)

    events = []
    async for ev in chat_stream_with_fallback(
        messages=[{"role": "user", "content": "hi"}],
        tier="primary",
        temperature=0.7,
        max_tokens=100,
    ):
        events.append(ev)

    assert events[-1]["full"] == "ok"
    assert fake.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_chat_stream_can_disable_thinking_for_light_mimo_tasks(monkeypatch):
    from app.llm.client import chat_stream_with_fallback
    from app.llm import client as c
    fake = _FakeClient({c.settings.llm_model: lambda: _mk_stream(["ok"], tokens=2)})
    _patch_client(monkeypatch, fake)

    events = []
    async for ev in chat_stream_with_fallback(
        messages=[{"role": "user", "content": "hi"}],
        tier="primary",
        temperature=0.7,
        max_tokens=100,
        disable_thinking=True,
    ):
        events.append(ev)

    assert events[-1]["full"] == "ok"
    assert fake.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}


@pytest.mark.asyncio
async def test_chat_once_with_fallback_enables_thinking_for_deepseek_json_tasks(monkeypatch):
    from app.llm.client import chat_once_with_fallback
    from app.llm import client as c
    monkeypatch.setattr(c.settings, "llm_fast_model", "deepseek-v4-pro")
    fake = _FakeOneShotClient()
    _patch_client(monkeypatch, fake)

    text, model = await chat_once_with_fallback(
        messages=[{"role": "user", "content": "json please"}],
        tier="fast",
        temperature=0,
        max_tokens=200,
    )

    assert text == '{"ok":true}'
    assert model == "deepseek-v4-pro"
    assert fake.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_chat_once_with_fallback_enables_thinking_for_mimo_json_tasks(monkeypatch):
    from app.llm.client import chat_once_with_fallback
    fake = _FakeOneShotClient()
    _patch_client(monkeypatch, fake)

    text, model = await chat_once_with_fallback(
        messages=[{"role": "user", "content": "json please"}],
        tier="fast",
        temperature=0,
        max_tokens=200,
    )

    assert text == '{"ok":true}'
    assert model == "mimo-v2.5"
    assert fake.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


def test_client_has_max_retries_zero():
    """openai SDK must be constructed with max_retries=0 so our fallback controls retries."""
    from app.llm import client as c
    assert c._client.max_retries == 0
