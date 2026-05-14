"""Helpers for consuming SSE + stubbing openai client in integration tests."""
from __future__ import annotations

import json
from types import SimpleNamespace


def patch_llm_client(monkeypatch, prescribed: dict[str, list[str]],
                     *, raise_on_model: set[str] | None = None):
    """Replace app.llm.client._client.chat.completions.create with a stub.

    prescribed: {model_name: [delta1, delta2, ...]}.  Missing streaming model → raises.
    raise_on_model: these model names raise to force fallback.
    """
    raise_on_model = set(raise_on_model or set())

    from app.llm import client as c

    # Keep older tests focused on behavior rather than provider naming. Some
    # fixtures still describe the old MiMo primary/fast slots.
    model_aliases = {
        "mimo-v2-pro": {c.settings.llm_model},
        "mimo-v2-flash": {c.settings.llm_fast_model, c.settings.llm_fallback_model},
    }
    prescribed = dict(prescribed)
    for legacy, currents in model_aliases.items():
        for current in currents:
            if legacy in prescribed and current not in prescribed:
                prescribed[current] = prescribed[legacy]
    for legacy, currents in model_aliases.items():
        if legacy in raise_on_model:
            raise_on_model.update(currents)

    class _Message:
        def __init__(self, content: str):
            self.content = content
            self.reasoning_content = ""

    class _OneShot:
        def __init__(self, content: str, tokens=30):
            self.choices = [SimpleNamespace(
                message=_Message(content),
                finish_reason="stop",
            )]
            self.usage = SimpleNamespace(
                prompt_tokens=tokens // 3,
                completion_tokens=tokens - tokens // 3,
                total_tokens=tokens,
            )

    class _Chunk:
        def __init__(self, c):
            self.choices = [SimpleNamespace(delta=SimpleNamespace(content=c),
                                             finish_reason=None)]
            self.usage = None

    class _Final:
        def __init__(self, tokens=30):
            self.choices = [SimpleNamespace(delta=SimpleNamespace(content=""),
                                             finish_reason="stop")]
            self.usage = SimpleNamespace(
                prompt_tokens=tokens // 3,
                completion_tokens=tokens - tokens // 3,
                total_tokens=tokens,
            )

    def _router_response(messages) -> str:
        from app.prompts.router import classify_by_keywords

        current = ""
        if messages:
            current = str(messages[-1].get("content") or "")
        routed = classify_by_keywords(current) or {
            "intent": "other",
            "reason": "test_router_default",
            "artifact": {"enabled": False, "kind": None, "reason": ""},
        }
        return json.dumps({
            "intent": routed["intent"],
            "reason": routed["reason"],
            "artifact": routed.get("artifact") or {
                "enabled": False,
                "kind": None,
                "reason": "",
            },
        }, ensure_ascii=False)

    async def _create(*, model, stream, messages=None, **kw):
        if model in raise_on_model:
            raise RuntimeError(f"forced failure on {model}")
        if stream is False:
            if model in prescribed:
                return _OneShot("".join(prescribed[model]))
            if model == c.settings.llm_fast_model:
                return _OneShot(_router_response(messages or []))
            raise RuntimeError(f"no prescribed output for model {model}")
        if model not in prescribed:
            raise RuntimeError(f"no prescribed output for model {model}")
        chunks = prescribed[model]
        async def _gen():
            for d in chunks:
                yield _Chunk(d)
            yield _Final()
        return _gen()

    monkeypatch.setattr(c._client.chat.completions, "create", _create)


async def consume_sse(client, url, *, cookies=None, json_body=None):
    """httpx AsyncClient streaming GET/POST; parse `data: {json}\\n\\n` events."""
    events = []
    method = "POST" if json_body is not None else "GET"
    async with client.stream(method, url, cookies=cookies or {}, json=json_body) as r:
        assert r.status_code == 200, await r.aread()
        buf = ""
        async for chunk in r.aiter_text():
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                if frame.startswith("data: "):
                    events.append(json.loads(frame[len("data: "):]))
    return events
