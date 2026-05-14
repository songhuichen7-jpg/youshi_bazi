"""Integration: chat_message quota — pre-check 429 + race-on-commit error."""
from __future__ import annotations

import uuid

import pytest
from app.core.quotas import QUOTAS, today_beijing
from app.services.exceptions import QuotaExceededError
from app.services.quota import QuotaTicket
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.conftest import register_user
from tests.integration.test_sse_helpers import consume_sse, patch_llm_client


pytestmark = pytest.mark.asyncio


async def _make_chart(client, cookie):
    body = {"birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"}}
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    return r.json()["chart"]["id"]


async def test_chat_quota_precheck_429(client, database_url):
    cookie, user = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    chart_id = await _make_chart(client, cookie)
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    limit = QUOTAS[user["plan"]]["chat_message"]
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await s.execute(text("""
            INSERT INTO quota_usage (user_id, period, kind, count, updated_at)
            VALUES (:uid, :p, 'chat_message', :c, now())
            ON CONFLICT (user_id, period, kind) DO UPDATE SET count = EXCLUDED.count
        """), {"uid": user["id"], "p": today_beijing(), "c": limit})
        await s.commit()
    await engine.dispose()

    r2 = await client.post(
        f"/api/conversations/{conv_id}/messages",
        cookies={"session": cookie},
        json={"message": "你好"},
    )
    assert r2.status_code == 429
    assert r2.json()["detail"]["code"] == "QUOTA_EXCEEDED"
    assert "retry-after" in {k.lower() for k in r2.headers.keys()}


async def test_chat_quota_race_on_commit_emits_error_no_assistant(client, monkeypatch):
    """If a concurrent request consumes the last quota slot during expert streaming,
    ticket.commit() raises and we emit error instead of done. No assistant row written."""
    cookie, user = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    chart_id = await _make_chart(client, cookie)
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    patch_llm_client(monkeypatch, {"mimo-v2-pro": ["partial response"]})

    # Patch QuotaTicket.commit to raise the race exception
    async def _race_commit(self):
        raise QuotaExceededError(kind="chat_message", limit=30)

    monkeypatch.setattr(QuotaTicket, "commit", _race_commit)

    events = await consume_sse(client, f"/api/conversations/{conv_id}/messages",
                                cookies={"session": cookie},
                                json_body={"message": "我想换工作"})  # career keyword

    types = [e["type"] for e in events]
    assert types[-1] == "error"
    assert events[-1]["code"] == "QUOTA_EXCEEDED"

    r2 = await client.get(f"/api/conversations/{conv_id}/messages",
                           cookies={"session": cookie})
    roles = [m["role"] for m in r2.json()["items"]]
    assert "assistant" not in roles  # only user remains
