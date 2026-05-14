"""Integration: POST /gua happy path (cast + LLM + role='gua' message)."""
from __future__ import annotations

import uuid

import pytest
from tests.integration.conftest import register_user
from tests.integration.test_sse_helpers import consume_sse, patch_llm_client


pytestmark = pytest.mark.asyncio


async def _make_chart(client, cookie):
    body = {"birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"}}
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    return r.json()["chart"]["id"]


async def test_gua_happy_path(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    chart_id = await _make_chart(client, cookie)
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    patch_llm_client(monkeypatch, {"mimo-v2-pro": ["§卦象\n", "雷雨同作", "\n\n§原文\n> 卦辞..."]})

    events = await consume_sse(client, f"/api/conversations/{conv_id}/gua",
                                cookies={"session": cookie},
                                json_body={"question": "该不该跳槽"})

    types = [e["type"] for e in events]
    assert types[0] == "gua"
    gua_event = events[0]
    assert "name" in gua_event["data"] and "guaci" in gua_event["data"]
    assert "model" in types and "delta" in types
    assert types[-1] == "done"

    r2 = await client.get(f"/api/conversations/{conv_id}/messages",
                           cookies={"session": cookie})
    items = r2.json()["items"]
    roles = [m["role"] for m in items]
    assert roles == ["gua"]
    g = items[0]
    assert g["content"] is None
    assert "gua" in g["meta"] and g["meta"]["question"] == "该不该跳槽"
    assert g["meta"]["body"].startswith("§卦象")
