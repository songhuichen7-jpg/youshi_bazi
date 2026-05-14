"""quota.get_snapshot: merges QUOTAS[plan] with today's usage."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def db_session(database_url):
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            maker = async_sessionmaker(bind=conn, expire_on_commit=False)
            async with maker() as s:
                yield s
            await trans.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def user(db_session):
    from app.models.user import User
    u = User(phone=f"+86138{uuid.uuid4().int % 10**8:08d}",
             dek_ciphertext=b"\x00" * 44)
    db_session.add(u); await db_session.flush()
    return u


@pytest.mark.asyncio
async def test_snapshot_empty_returns_all_kinds_used_0(db_session, user):
    # NOTE: migration 0008 把 plan 集合从 {free, pro} 重命名成
    # {lite, standard, pro}，新用户默认 'lite'。这条测试当时没改。
    from app.services.quota import get_snapshot
    snap = await get_snapshot(db_session, user)
    assert snap.plan == "lite"
    assert set(snap.usage.keys()) == {"chat_message","section_regen","verdicts_regen",
                                       "dayun_regen","liunian_regen","gua","sms_send"}
    for u in snap.usage.values():
        assert u.used == 0


@pytest.mark.asyncio
async def test_snapshot_reflects_partial_usage(db_session, user):
    from app.core.quotas import today_beijing
    from app.services.quota import get_snapshot
    await db_session.execute(text("""
        INSERT INTO quota_usage (user_id, period, kind, count, updated_at)
        VALUES (:uid, :p, 'chat_message', 3, now())
    """), {"uid": user.id, "p": today_beijing()})
    await db_session.flush()
    snap = await get_snapshot(db_session, user)
    assert snap.usage["chat_message"].used == 3
    assert snap.usage["gua"].used == 0


@pytest.mark.asyncio
async def test_snapshot_resets_at_is_next_midnight_beijing(db_session, user):
    from zoneinfo import ZoneInfo
    from app.services.quota import get_snapshot
    snap = await get_snapshot(db_session, user)
    ra = snap.usage["chat_message"].resets_at
    beijing = ra.astimezone(ZoneInfo("Asia/Shanghai"))
    assert beijing.hour == 0 and beijing.minute == 0 and beijing.second == 0
