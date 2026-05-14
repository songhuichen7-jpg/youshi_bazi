"""chart.recompute: re-runs paipan + clears chart_cache."""
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
async def seeded(db_session):
    from app.db_types import user_dek_context
    from app.models.chart import Chart, ChartCache
    from app.models.user import User
    dek = os.urandom(32)
    u = User(phone=f"+86138{uuid.uuid4().int % 10**8:08d}",
             dek_ciphertext=b"\x00" * 44)
    db_session.add(u); await db_session.flush()
    with user_dek_context(dek):
        c = Chart(
            user_id=u.id,
            birth_input={"year":1990,"month":5,"day":12,"hour":14,
                         "minute":0,"gender":"male",
                         "useTrueSolarTime":True,"ziConvention":"early"},
            paipan={"sizhu":{"year":"old"}, "hourUnknown": False},
            engine_version="0.0.0",
        )
        db_session.add(c); await db_session.flush()
        cc = ChartCache(chart_id=c.id, kind="verdicts", key="",
                         content="stale", model_used="mimo-v2-pro",
                         tokens_used=10, regen_count=0)
        db_session.add(cc); await db_session.flush()
    return u, c, dek


@pytest.mark.asyncio
async def test_recompute_updates_paipan_and_engine_version(db_session, seeded):
    from app.db_types import user_dek_context
    from app.services.chart import recompute
    import paipan
    user, chart, dek = seeded
    with user_dek_context(dek):
        updated, warnings = await recompute(db_session, user, chart.id)
    assert updated.engine_version == paipan.VERSION
    assert updated.paipan.get("sizhu") != {"year":"old"}


@pytest.mark.asyncio
async def test_recompute_clears_chart_cache(db_session, seeded):
    from app.db_types import user_dek_context
    from app.services.chart import recompute
    user, chart, dek = seeded
    with user_dek_context(dek):
        await recompute(db_session, user, chart.id)
    await db_session.flush()
    n = (await db_session.execute(
        text("SELECT count(*) FROM chart_cache WHERE chart_id = :cid"),
        {"cid": chart.id},
    )).scalar()
    assert n == 0


@pytest.mark.asyncio
async def test_recompute_soft_deleted_raises_not_found(db_session, seeded):
    from app.db_types import user_dek_context
    from app.services.chart import recompute
    from app.services.exceptions import ChartNotFound
    user, chart, dek = seeded
    await db_session.execute(
        text("UPDATE charts SET deleted_at=now() WHERE id=:cid"),
        {"cid": chart.id},
    )
    await db_session.flush()
    with user_dek_context(dek):
        with pytest.raises(ChartNotFound):
            await recompute(db_session, user, chart.id)
