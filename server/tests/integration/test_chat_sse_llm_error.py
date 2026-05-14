"""Integration: chat expert LLM error keeps user row, no assistant, no quota commit."""
from __future__ import annotations

import uuid

import pytest
from app.core.quotas import today_beijing
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.conftest import register_user
from tests.integration.test_sse_helpers import consume_sse, patch_llm_client


pytestmark = pytest.mark.asyncio


async def _make_chart(client, cookie):
    body = {"birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"}}
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    return r.json()["chart"]["id"]


async def test_chat_llm_error_keeps_user_no_assistant(client, monkeypatch, database_url):
    cookie, user = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    chart_id = await _make_chart(client, cookie)
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    # Both primary + fallback raise → expert stream errors out
    patch_llm_client(monkeypatch,
                      {"mimo-v2-pro": [], "mimo-v2-flash": []},
                      raise_on_model={"mimo-v2-pro", "mimo-v2-flash"})

    events = await consume_sse(client, f"/api/conversations/{conv_id}/messages",
                                cookies={"session": cookie},
                                json_body={"message": "我想换工作"})  # career keyword

    types = [e["type"] for e in events]
    assert types[-1] == "error"

    r2 = await client.get(f"/api/conversations/{conv_id}/messages",
                           cookies={"session": cookie})
    roles = [m["role"] for m in r2.json()["items"]]
    assert roles == ["user"]  # assistant NOT written

    # Quota NOT charged
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        row = (await s.execute(text("""
            SELECT count FROM quota_usage
             WHERE user_id = :uid AND period = :p AND kind = 'chat_message'
        """), {"uid": user["id"], "p": today_beijing()})).first()
    await engine.dispose()
    assert row is None or row[0] == 0
