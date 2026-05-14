"""Integration: POST /messages happy path (router → expert → assistant row)."""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
from app.llm import client as llm_client_mod
from tests.integration.conftest import register_user
from tests.integration.test_sse_helpers import consume_sse, patch_llm_client


pytestmark = pytest.mark.asyncio


async def _make_chart(client, cookie):
    body = {"birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"}}
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    return r.json()["chart"]["id"]


async def test_chat_message_happy_path(client, monkeypatch):
    """Fast router (career) → expert stream → assistant row + done."""
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    chart_id = await _make_chart(client, cookie)
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    patch_llm_client(monkeypatch, {"mimo-v2-pro": ["你想问的", "事业", "方向"]})

    events = await consume_sse(client, f"/api/conversations/{conv_id}/messages",
                                cookies={"session": cookie},
                                json_body={"message": "我想换工作", "bypass_divination": False})

    types = [e["type"] for e in events]
    assert types[0] == "intent"
    assert events[0]["intent"] == "career"
    assert events[0]["source"] == "llm"
    assert "model" in types and "delta" in types
    assert types[-1] == "done"
    assert events[-1]["full"] == "你想问的事业方向"

    r2 = await client.get(f"/api/conversations/{conv_id}/messages",
                           cookies={"session": cookie})
    items = r2.json()["items"]
    roles = [m["role"] for m in items]
    # newest-first
    assert roles == ["assistant", "user"]
    assert items[0]["content"] == "你想问的事业方向"
    assert items[1]["content"] == "我想换工作"


async def test_chat_message_loads_history_in_second_turn(client, monkeypatch):
    """Second message includes prior turn in expert prompt (verified by capturing messages)."""
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    chart_id = await _make_chart(client, cookie)
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    # Turn 1
    patch_llm_client(monkeypatch, {"mimo-v2-pro": ["A1"]})
    await consume_sse(client, f"/api/conversations/{conv_id}/messages",
                       cookies={"session": cookie},
                       json_body={"message": "事业方向 A"})

    # Turn 2 — capture messages sent to LLM
    captured: list[list[dict]] = []

    async def _capture_create(*, model, stream, messages, **kw):
        captured.append(messages)
        # Replay the stub behavior
        async def _gen():
            class _Chunk:
                def __init__(self, c):
                    self.choices = [SimpleNamespace(
                        delta=SimpleNamespace(content=c), finish_reason=None)]
                    self.usage = None
            class _Final:
                def __init__(self):
                    self.choices = [SimpleNamespace(
                        delta=SimpleNamespace(content=""), finish_reason="stop")]
                    self.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20, total_tokens=30)
            yield _Chunk("A2")
            yield _Final()
        return _gen()

    monkeypatch.setattr(llm_client_mod._client.chat.completions, "create", _capture_create)

    await consume_sse(client, f"/api/conversations/{conv_id}/messages",
                       cookies={"session": cookie},
                       json_body={"message": "事业方向 B"})

    # Inspect captured messages for prior turn content
    assert len(captured) >= 1
    full_text = json.dumps(captured, ensure_ascii=False)
    assert "事业方向 A" in full_text
    assert "A1" in full_text
