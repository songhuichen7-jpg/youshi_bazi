"""chart_llm cache helpers: get_cache_row + upsert_cache."""
from __future__ import annotations

import os
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
async def user_and_chart(db_session):
    from app.db_types import user_dek_context
    from app.models.chart import Chart
    from app.models.user import User
    dek = os.urandom(32)
    u = User(phone=f"+86138{uuid.uuid4().int % 10**8:08d}",
             dek_ciphertext=b"\x00" * 44)
    db_session.add(u); await db_session.flush()
    with user_dek_context(dek):
        c = Chart(
            user_id=u.id,
            birth_input={"year":1990,"month":5,"day":12,"hour":12,"gender":"male"},
            paipan={"sizhu":"...","hourUnknown":False},
            engine_version="0.1.0",
        )
        db_session.add(c); await db_session.flush()
    return u, c, dek


@pytest.mark.asyncio
async def test_get_cache_row_returns_none_when_empty(db_session, user_and_chart):
    from app.services.chart_llm import get_cache_row
    _, chart, _ = user_and_chart
    row = await get_cache_row(db_session, chart.id, "verdicts", "")
    assert row is None


@pytest.mark.asyncio
async def test_upsert_cache_inserts_new(db_session, user_and_chart):
    from app.db_types import user_dek_context
    from app.services.chart_llm import get_cache_row, upsert_cache
    _, chart, dek = user_and_chart
    with user_dek_context(dek):
        await upsert_cache(db_session,
            chart_id=chart.id, kind="verdicts", key="",
            content="hello world", model_used="mimo-v2-pro",
            tokens_used=42, regen_increment=False)
        await db_session.flush()
        row = await get_cache_row(db_session, chart.id, "verdicts", "")
    assert row is not None
    assert row.content == "hello world"
    assert row.model_used == "mimo-v2-pro"
    assert row.tokens_used == 42
    assert row.regen_count == 0


@pytest.mark.asyncio
async def test_upsert_cache_replaces_existing(db_session, user_and_chart):
    from app.db_types import user_dek_context
    from app.services.chart_llm import get_cache_row, upsert_cache
    _, chart, dek = user_and_chart
    with user_dek_context(dek):
        await upsert_cache(db_session,
            chart_id=chart.id, kind="verdicts", key="",
            content="v1", model_used="mimo-v2-pro",
            tokens_used=10, regen_increment=False)
        await db_session.flush()
        await upsert_cache(db_session,
            chart_id=chart.id, kind="verdicts", key="",
            content="v2", model_used="mimo-v2-flash",
            tokens_used=20, regen_increment=True)
        await db_session.flush()
        row = await get_cache_row(db_session, chart.id, "verdicts", "")
    assert row.content == "v2"
    assert row.model_used == "mimo-v2-flash"
    assert row.regen_count == 1
