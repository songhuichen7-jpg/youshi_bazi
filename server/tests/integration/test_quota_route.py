"""GET /api/quota."""
from __future__ import annotations

import uuid

import pytest
from tests.integration.conftest import register_user


@pytest.mark.asyncio
async def test_quota_unauthenticated_401(client):
    r = await client.get("/api/quota")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_quota_happy(client):
    # NOTE: migration 0008 把 plan 集合改成 {lite, standard, pro};0015 内测期
    # 应用层把新注册用户默认升到 'pro' (services/auth.py),让试用者拿到完整
    # 配额。付费上线时去掉 services 里的覆盖,这里相应改回 'lite'。
    cookie, user = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    r = await client.get("/api/quota", cookies={"session": cookie})
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "pro"
    assert set(body["usage"].keys()) == {"chat_message","section_regen","verdicts_regen",
                                          "dayun_regen","liunian_regen","gua","sms_send"}
    for v in body["usage"].values():
        assert v["used"] == 0
        assert v["limit"] > 0
        assert "resets_at" in v


@pytest.mark.asyncio
async def test_quota_reflects_sms_usage(client, database_url):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.core.quotas import today_beijing

    cookie, user = await register_user(client, f"+86139{uuid.uuid4().int % 10**8:08d}")

    # Directly seed a quota_usage row so we can assert the snapshot surfaces it.
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await s.execute(text("""
            INSERT INTO quota_usage (user_id, period, kind, count, updated_at)
            VALUES (:uid, :p, 'sms_send', 1, now())
        """), {"uid": user["id"], "p": today_beijing()})
        await s.commit()
    await engine.dispose()

    r = await client.get("/api/quota", cookies={"session": cookie})
    assert r.json()["usage"]["sms_send"]["used"] == 1
