"""app.llm.logs.insert_llm_usage_log: sync INSERT, try/except wrapped."""
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
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.mark.asyncio
async def test_insert_llm_usage_log_happy(db_session, user):
    from app.llm.logs import insert_llm_usage_log
    await insert_llm_usage_log(
        db_session, user_id=user.id, chart_id=None,
        endpoint="verdicts", model="mimo-v2-pro",
        prompt_tokens=100, completion_tokens=500, duration_ms=2500,
    )
    row = (await db_session.execute(
        text("SELECT endpoint, model, prompt_tokens, completion_tokens, duration_ms "
             "FROM llm_usage_logs WHERE user_id = :uid"), {"uid": user.id},
    )).one()
    assert row.endpoint == "verdicts"
    assert row.model == "mimo-v2-pro"
    assert row.prompt_tokens == 100
    assert row.completion_tokens == 500
    assert row.duration_ms == 2500


@pytest.mark.asyncio
async def test_insert_llm_usage_log_error_field(db_session, user):
    from app.llm.logs import insert_llm_usage_log
    await insert_llm_usage_log(
        db_session, user_id=user.id, chart_id=None,
        endpoint="sections", model=None,
        prompt_tokens=None, completion_tokens=None, duration_ms=1200,
        error="both models failed",
    )
    row = (await db_session.execute(
        text("SELECT error FROM llm_usage_logs WHERE user_id = :uid"), {"uid": user.id},
    )).one()
    assert row.error == "both models failed"


@pytest.mark.asyncio
async def test_insert_llm_usage_log_swallows_db_error(db_session, user, monkeypatch):
    from app.llm import logs as logs_mod
    async def _boom(*a, **kw):
        raise RuntimeError("DB down")
    monkeypatch.setattr(db_session, "execute", _boom)
    # Must NOT raise
    await logs_mod.insert_llm_usage_log(
        db_session, user_id=user.id, chart_id=None,
        endpoint="x", model="y", prompt_tokens=0, completion_tokens=0, duration_ms=0,
    )
