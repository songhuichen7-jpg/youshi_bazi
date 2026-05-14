"""chart service — list_charts / get_chart (with soft-delete window) / get_cache_slots."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

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
            async with maker() as session:
                yield session
            await trans.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def user_and_dek(db_session):
    # NOTE: pro 档位 — 同 test_chart_service_create.py，lite 默认 chart_max=2
    # 会让 list/sort 测试创建第 3 张时撞上限。
    from app.models.user import User
    dek = os.urandom(32)
    u = User(
        phone=f"+86138{uuid.uuid4().int % 10**8:08d}",
        dek_ciphertext=b"\x00" * 44,
        plan="pro",
    )
    db_session.add(u)
    await db_session.flush()
    return u, dek


async def _make_chart(db_session, user, label=None):
    from app.db_types import user_dek_context
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service
    req = ChartCreateRequest(
        birth_input=BirthInput(year=1990, month=5, day=12, hour=12, gender="male"),
        label=label,
    )
    return (await chart_service.create_chart(db_session, user, req))[0]


@pytest.mark.asyncio
async def test_list_charts_empty(db_session, user_and_dek):
    from app.services import chart as chart_service
    user, _ = user_and_dek
    rows = await chart_service.list_charts(db_session, user)
    assert rows == []


@pytest.mark.asyncio
async def test_list_charts_happy_desc(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    user, dek = user_and_dek
    with user_dek_context(dek):
        a = await _make_chart(db_session, user, label="A")
        b = await _make_chart(db_session, user, label="B")
        c = await _make_chart(db_session, user, label="C")
        rows = await chart_service.list_charts(db_session, user)
    ids = [r.id for r in rows]
    # DESC by created_at; c newest first
    assert ids == [c.id, b.id, a.id]


@pytest.mark.asyncio
async def test_list_charts_excludes_soft_deleted(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    user, dek = user_and_dek
    with user_dek_context(dek):
        a = await _make_chart(db_session, user, label="keep")
        b = await _make_chart(db_session, user, label="gone")
        await db_session.execute(
            text("UPDATE charts SET deleted_at = now() WHERE id = :cid"), {"cid": b.id},
        )
        await db_session.flush()
        rows = await chart_service.list_charts(db_session, user)
    assert len(rows) == 1
    assert rows[0].id == a.id


@pytest.mark.asyncio
async def test_list_charts_isolated_per_user(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.models.user import User
    from app.services import chart as chart_service
    user_a, dek_a = user_and_dek
    # Second user
    user_b = User(phone=f"+86139{uuid.uuid4().int % 10**8:08d}",
                  dek_ciphertext=b"\x00" * 44)
    db_session.add(user_b)
    await db_session.flush()
    dek_b = os.urandom(32)

    with user_dek_context(dek_a):
        await _make_chart(db_session, user_a, label="A")
    with user_dek_context(dek_b):
        await _make_chart(db_session, user_b, label="B")
        rows_b = await chart_service.list_charts(db_session, user_b)
    with user_dek_context(dek_a):
        rows_a = await chart_service.list_charts(db_session, user_a)
    assert len(rows_a) == 1 and rows_a[0].label == "A"
    assert len(rows_b) == 1 and rows_b[0].label == "B"


@pytest.mark.asyncio
async def test_get_chart_happy(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user, label="X")
        got = await chart_service.get_chart(db_session, user, c.id)
    assert got.id == c.id
    assert got.label == "X"


@pytest.mark.asyncio
async def test_get_chart_nonexistent_raises(db_session, user_and_dek):
    from app.services import chart as chart_service
    from app.services.exceptions import ChartNotFound
    user, _ = user_and_dek
    with pytest.raises(ChartNotFound):
        await chart_service.get_chart(db_session, user, uuid.uuid4())


@pytest.mark.asyncio
async def test_get_chart_wrong_owner_raises(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.models.user import User
    from app.services import chart as chart_service
    from app.services.exceptions import ChartNotFound

    user_a, dek_a = user_and_dek
    user_b = User(phone=f"+86139{uuid.uuid4().int % 10**8:08d}",
                  dek_ciphertext=b"\x00" * 44)
    db_session.add(user_b)
    await db_session.flush()

    with user_dek_context(dek_a):
        c = await _make_chart(db_session, user_a)
    with pytest.raises(ChartNotFound):
        await chart_service.get_chart(db_session, user_b, c.id)


@pytest.mark.asyncio
async def test_get_chart_soft_deleted_default_404(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    from app.services.exceptions import ChartNotFound
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user)
        await db_session.execute(
            text("UPDATE charts SET deleted_at = now() WHERE id = :cid"), {"cid": c.id},
        )
        await db_session.flush()
        with pytest.raises(ChartNotFound):
            await chart_service.get_chart(db_session, user, c.id)


@pytest.mark.asyncio
async def test_get_chart_include_soft_deleted_within_window(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user)
        await db_session.execute(
            text("UPDATE charts SET deleted_at = now() WHERE id = :cid"), {"cid": c.id},
        )
        await db_session.flush()
        got = await chart_service.get_chart(db_session, user, c.id, include_soft_deleted=True)
    assert got.id == c.id
    assert got.deleted_at is not None


@pytest.mark.asyncio
async def test_get_chart_soft_deleted_past_window_404(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    from app.services.exceptions import ChartNotFound
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user)
        # Simulate 31 days ago.
        await db_session.execute(
            text("UPDATE charts SET deleted_at = now() - INTERVAL '31 days' WHERE id = :cid"),
            {"cid": c.id},
        )
        await db_session.flush()
        with pytest.raises(ChartNotFound):
            await chart_service.get_chart(db_session, user, c.id, include_soft_deleted=True)


@pytest.mark.asyncio
async def test_get_cache_slots_empty(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user)
        slots = await chart_service.get_cache_slots(db_session, c.id)
    # Plan 4: chart_cache table always empty → []
    assert slots == []
