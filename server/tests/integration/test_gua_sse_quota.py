"""Integration: gua quota pre-check 429."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.conftest import register_user


pytestmark = pytest.mark.asyncio


async def test_gua_quota_precheck_429_when_saturated(client, monkeypatch):
    """If the user has already hit the gua quota, /gua returns 429.

    This implicitly verifies check_quota("gua") resolves correctly (vs. the
    earlier "gua_cast" typo that would have raised KeyError).
    """
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, user = await register_user(client, phone)

    # Create a chart + conversation
    r = await client.post("/api/charts", cookies={"session": cookie}, json={
        "birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"},
    })
    chart_id = r.json()["chart"]["id"]
    r = await client.post(f"/api/charts/{chart_id}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]

    # Saturate the gua quota directly in the DB
    from app.core.quotas import QUOTAS, today_beijing
    limit = QUOTAS[user["plan"]]["gua"]
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text("""
            INSERT INTO quota_usage (user_id, period, kind, count, updated_at)
            VALUES (:uid, :p, 'gua', :c, now())
            ON CONFLICT (user_id, period, kind) DO UPDATE SET count = EXCLUDED.count
        """), {"uid": user["id"], "p": today_beijing(), "c": limit})
        await s.commit()
    await engine.dispose()

    # Hit /gua — should pre-check 429 (NOT KeyError; NOT 200 SSE)
    r = await client.post(
        f"/api/conversations/{conv_id}/gua",
        cookies={"session": cookie},
        json={"question": "test"},
    )
    assert r.status_code == 429, r.text
    assert r.json()["detail"]["code"] == "QUOTA_EXCEEDED"
