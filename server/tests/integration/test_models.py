"""Per-model smoke tests under user_dek_context.

Chart / Conversation / Message have EncryptedJSONB / EncryptedText columns
after Task 11; they require an active user_dek_context for both insert and
select.  User.dek_ciphertext is KEK-wrapped (LargeBinary at SQL level) and
does NOT need DEK context — users-only operations work outside context.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


@pytest.fixture
async def db_session(database_url):
    engine = create_async_engine(database_url)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session_maker = async_sessionmaker(bind=conn, expire_on_commit=False)
        async with session_maker() as session:
            yield session
        await trans.rollback()
    await engine.dispose()


@pytest.fixture
def test_dek() -> bytes:
    return os.urandom(32)


async def test_insert_user(db_session: AsyncSession):
    """users.dek_ciphertext is LargeBinary (KEK-wrapped) — no DEK context needed."""
    # NOTE: migration 0008 — plan 集合从 {free, pro} → {lite, standard, pro}，
    # 新用户 server_default 是 'lite'。
    from app.models import User
    u = User(phone="+8613800000001", dek_ciphertext=b"\x00" * 44)
    db_session.add(u)
    await db_session.flush()
    assert u.id is not None
    assert u.status == "active"
    assert u.role == "user"
    assert u.plan == "lite"


async def test_insert_chart_with_fk_user(db_session: AsyncSession, test_dek):
    """Chart.birth_input / .paipan are EncryptedJSONB → DEK context required."""
    from app.db_types import user_dek_context
    from app.models import Chart, User

    u = User(phone="+8613800000002", dek_ciphertext=b"\x00" * 44)
    db_session.add(u)
    await db_session.flush()

    with user_dek_context(test_dek):
        c = Chart(
            user_id=u.id,
            birth_input={"year": 1990, "month": 5, "day": 15},
            paipan={"sizhu": {"year": "庚午"}},
            engine_version="0.1.0",
        )
        db_session.add(c)
        await db_session.flush()
        assert c.id is not None
        # Round-trip still works inside the same context.
        await db_session.refresh(c)
        assert c.birth_input["year"] == 1990


async def test_cascade_delete_messages(db_session: AsyncSession, test_dek):
    """Deleting a Conversation cascades to its Messages (ondelete='CASCADE')."""
    from sqlalchemy import delete, select

    from app.db_types import user_dek_context
    from app.models import Chart, Conversation, Message, User

    u = User(phone="+8613800000003", dek_ciphertext=b"\x00" * 44)
    db_session.add(u)
    await db_session.flush()

    with user_dek_context(test_dek):
        c = Chart(user_id=u.id, birth_input={}, paipan={}, engine_version="0.1.0")
        db_session.add(c)
        await db_session.flush()
        conv = Conversation(chart_id=c.id)
        db_session.add(conv)
        await db_session.flush()
        m = Message(conversation_id=conv.id, role="user", content="hi")
        db_session.add(m)
        await db_session.flush()
        message_id = m.id

    # Deletion itself doesn't touch encrypted columns — no DEK context needed.
    await db_session.execute(delete(Conversation).where(Conversation.id == conv.id))
    await db_session.flush()

    found = await db_session.execute(select(Message).where(Message.id == message_id))
    assert found.scalar_one_or_none() is None


async def test_unique_chart_cache_slot(db_session: AsyncSession, test_dek):
    """UNIQUE (chart_id, kind, key) on chart_cache."""
    from sqlalchemy.exc import IntegrityError

    from app.db_types import user_dek_context
    from app.models import Chart, ChartCache, User

    u = User(phone="+8613800000004", dek_ciphertext=b"\x00" * 44)
    db_session.add(u)
    await db_session.flush()

    with user_dek_context(test_dek):
        c = Chart(user_id=u.id, birth_input={}, paipan={}, engine_version="0.1.0")
        db_session.add(c)
        await db_session.flush()

        cc1 = ChartCache(chart_id=c.id, kind="section", key="career")
        db_session.add(cc1)
        await db_session.flush()

        cc2 = ChartCache(chart_id=c.id, kind="section", key="career")
        db_session.add(cc2)
        with pytest.raises(IntegrityError):
            await db_session.flush()
