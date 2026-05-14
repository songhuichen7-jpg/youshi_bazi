"""Integration: divination redirect writes cta; bypass consumes cta."""
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


async def test_divination_redirects_and_writes_cta(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    chart_id = await _make_chart(client, cookie)
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    # No LLM expected — keyword "能不能" triggers divination + redirect
    # But just in case, install a boom that fails noisily if called
    from app.llm import client as c
    def _boom_sync(*a, **kw):
        raise AssertionError("expert LLM should not run on divination redirect")
    monkeypatch.setattr(c._client.chat.completions, "create", _boom_sync)

    events = await consume_sse(client, f"/api/conversations/{conv_id}/messages",
                                cookies={"session": cookie},
                                json_body={"message": "我能不能买这套房子"})

    types = [e["type"] for e in events]
    assert "redirect" in types
    redirect = next(e for e in events if e["type"] == "redirect")
    assert redirect["to"] == "gua"
    assert redirect["question"] == "我能不能买这套房子"
    assert types[-1] == "done"

    r2 = await client.get(f"/api/conversations/{conv_id}/messages",
                           cookies={"session": cookie})
    items = r2.json()["items"]
    roles = [m["role"] for m in items]
    assert roles == ["cta", "user"]
    assert items[0]["meta"]["question"] == "我能不能买这套房子"


async def test_bypass_divination_consumes_cta_and_writes_assistant(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    chart_id = await _make_chart(client, cookie)
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    # Turn 1 — fast router classifies divination, then writes a CTA.
    await consume_sse(client, f"/api/conversations/{conv_id}/messages",
                       cookies={"session": cookie},
                       json_body={"message": "我能不能换工作"})

    # Turn 2 — bypass divination triggers expert; needs LLM mock
    patch_llm_client(monkeypatch, {"mimo-v2-pro": ["分", "析"]})

    await consume_sse(client, f"/api/conversations/{conv_id}/messages",
                       cookies={"session": cookie},
                       json_body={"message": "用命盘分析就好",
                                   "bypass_divination": True})

    r2 = await client.get(f"/api/conversations/{conv_id}/messages",
                           cookies={"session": cookie})
    items = r2.json()["items"]
    roles = [m["role"] for m in items]
    assert "cta" not in roles
    assert roles[0] == "assistant"
