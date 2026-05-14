"""QuotaTicket unit tests — hits testcontainers Postgres."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.exceptions import QuotaExceededError
from app.services.quota import QuotaTicket


@pytest_asyncio.fixture
async def db_session(database_url):
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            maker = async_sessionmaker(bind=conn, expire_on_commit=False)
            async with maker() as session:
                yield session
            await trans.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def user(db_session):
    from app.models.user import User
    u = User(phone="+8613800009999", dek_ciphertext=b"\x00" * 44)
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.mark.asyncio
async def test_commit_increments_from_zero(db_session, user):
    from sqlalchemy import text
    ticket = QuotaTicket(user=user, kind="chat_message", limit=3, _db=db_session)
    count = await ticket.commit()
    assert count == 1

    row = (await db_session.execute(text("""
        SELECT count FROM quota_usage WHERE user_id=:uid AND kind='chat_message'
    """), {"uid": user.id})).scalar_one()
    assert row == 1


@pytest.mark.asyncio
async def test_commit_increments_existing(db_session, user):
    ticket_a = QuotaTicket(user=user, kind="chat_message", limit=3, _db=db_session)
    await ticket_a.commit()

    ticket_b = QuotaTicket(user=user, kind="chat_message", limit=3, _db=db_session)
    count = await ticket_b.commit()
    assert count == 2


@pytest.mark.asyncio
async def test_commit_fails_at_limit(db_session, user):
    # Prefill 3 with limit 3.
    for _ in range(3):
        await QuotaTicket(user=user, kind="chat_message", limit=3, _db=db_session).commit()

    # 4th commit must fail.
    bad = QuotaTicket(user=user, kind="chat_message", limit=3, _db=db_session)
    with pytest.raises(QuotaExceededError) as exc:
        await bad.commit()
    assert exc.value.details == {"kind": "chat_message", "limit": 3}


@pytest.mark.asyncio
async def test_rollback_decrements(db_session, user):
    from sqlalchemy import text
    ticket = QuotaTicket(user=user, kind="chat_message", limit=3, _db=db_session)
    await ticket.commit()
    await ticket.rollback()

    row = (await db_session.execute(text("""
        SELECT count FROM quota_usage WHERE user_id=:uid AND kind='chat_message'
    """), {"uid": user.id})).scalar_one()
    assert row == 0


@pytest.mark.asyncio
async def test_rollback_before_commit_is_noop(db_session, user):
    ticket = QuotaTicket(user=user, kind="chat_message", limit=3, _db=db_session)
    await ticket.rollback()   # should not raise
    # Nothing should be in the table.
    from sqlalchemy import text
    rows = (await db_session.execute(text("""
        SELECT count(*) FROM quota_usage WHERE user_id=:uid
    """), {"uid": user.id})).scalar_one()
    assert rows == 0


@pytest.mark.asyncio
async def test_double_commit_raises(db_session, user):
    ticket = QuotaTicket(user=user, kind="chat_message", limit=3, _db=db_session)
    await ticket.commit()
    with pytest.raises(RuntimeError, match="already committed"):
        await ticket.commit()
