"""Integration: gua endpoint consumes prior cta row."""
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


async def test_gua_after_divination_consumes_cta(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    chart_id = await _make_chart(client, cookie)
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    # Turn 1: fast router classifies divination → cta row written
    await consume_sse(client, f"/api/conversations/{conv_id}/messages",
                       cookies={"session": cookie},
                       json_body={"message": "我能不能换工作"})

    # Turn 2: cast gua → consumes the cta + INSERTs role='gua'
    patch_llm_client(monkeypatch, {"mimo-v2-pro": ["占算结果"]})
    await consume_sse(client, f"/api/conversations/{conv_id}/gua",
                       cookies={"session": cookie},
                       json_body={"question": "我能不能换工作"})

    r2 = await client.get(f"/api/conversations/{conv_id}/messages",
                           cookies={"session": cookie})
    roles = [m["role"] for m in r2.json()["items"]]
    # newest-first, cta consumed
    assert "cta" not in roles
    assert roles == ["gua", "user"]
