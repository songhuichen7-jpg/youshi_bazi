"""Integration: soft-delete + restore (within 30d window) + 410 outside."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.conftest import register_user


pytestmark = pytest.mark.asyncio


async def _register_with_chart(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    r = await client.post("/api/charts", cookies={"session": cookie}, json={
        "birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"},
    })
    return cookie, r.json()["chart"]["id"]


async def test_restore_within_window(client):
    cookie, cid = await _register_with_chart(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]
    await client.delete(f"/api/conversations/{conv_id}", cookies={"session": cookie})
    r2 = await client.post(f"/api/conversations/{conv_id}/restore",
                            cookies={"session": cookie})
    assert r2.status_code == 200
    assert r2.json()["deleted_at"] is None


async def test_restore_outside_window_410(client):
    cookie, cid = await _register_with_chart(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]
    await client.delete(f"/api/conversations/{conv_id}", cookies={"session": cookie})

    # Backdate deleted_at past 30 days using a fresh engine
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        old = datetime.now(tz=timezone.utc) - timedelta(days=31)
        await s.execute(
            text("UPDATE conversations SET deleted_at = :d WHERE id = :id"),
            {"d": old, "id": conv_id},
        )
        await s.commit()
    await engine.dispose()

    r2 = await client.post(f"/api/conversations/{conv_id}/restore",
                            cookies={"session": cookie})
    assert r2.status_code == 410
    assert r2.json()["detail"]["code"] == "CONVERSATION_GONE"
