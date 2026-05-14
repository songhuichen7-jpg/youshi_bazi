"""chart service — update_label / soft_delete / restore."""
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
            async with maker() as session:
                yield session
            await trans.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def user_and_dek(db_session):
    # NOTE: pro 档位 — write 测试要造 15+ 张 chart 验 cap，lite 默认 2 张就上限。
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
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service
    req = ChartCreateRequest(
        birth_input=BirthInput(year=1990, month=5, day=12, hour=12, gender="male"),
        label=label,
    )
    return (await chart_service.create_chart(db_session, user, req))[0]


@pytest.mark.asyncio
async def test_update_label_happy(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user, label="old")
        updated = await chart_service.update_label(db_session, user, c.id, "new")
    assert updated.label == "new"
    assert updated.id == c.id


@pytest.mark.asyncio
async def test_update_label_to_null(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user, label="old")
        updated = await chart_service.update_label(db_session, user, c.id, None)
    assert updated.label is None


@pytest.mark.asyncio
async def test_update_label_wrong_owner_404(db_session, user_and_dek):
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
        await chart_service.update_label(db_session, user_b, c.id, "evil")


@pytest.mark.asyncio
async def test_update_label_soft_deleted_404(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    from app.services.exceptions import ChartNotFound
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user)
        await chart_service.soft_delete(db_session, user, c.id)
        with pytest.raises(ChartNotFound):
            await chart_service.update_label(db_session, user, c.id, "nope")


@pytest.mark.asyncio
async def test_soft_delete_happy(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user)
        await chart_service.soft_delete(db_session, user, c.id)
    # Row still present but deleted_at set
    row = (await db_session.execute(
        text("SELECT deleted_at FROM charts WHERE id = :cid"), {"cid": c.id},
    )).scalar_one()
    assert row is not None


@pytest.mark.asyncio
async def test_soft_delete_already_deleted_raises(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    from app.services.exceptions import ChartAlreadyDeleted
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user)
        await chart_service.soft_delete(db_session, user, c.id)
        with pytest.raises(ChartAlreadyDeleted):
            await chart_service.soft_delete(db_session, user, c.id)


@pytest.mark.asyncio
async def test_soft_delete_wrong_owner_404(db_session, user_and_dek):
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
        await chart_service.soft_delete(db_session, user_b, c.id)


@pytest.mark.asyncio
async def test_restore_happy(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user, label="coming back")
        await chart_service.soft_delete(db_session, user, c.id)
        restored = await chart_service.restore(db_session, user, c.id)
    assert restored.id == c.id
    assert restored.deleted_at is None
    assert restored.label == "coming back"


@pytest.mark.asyncio
async def test_restore_not_deleted_404(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    from app.services.exceptions import ChartNotFound
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user)
        with pytest.raises(ChartNotFound):
            await chart_service.restore(db_session, user, c.id)


@pytest.mark.asyncio
async def test_restore_beyond_window_404(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    from app.services.exceptions import ChartNotFound
    user, dek = user_and_dek
    with user_dek_context(dek):
        c = await _make_chart(db_session, user)
        await db_session.execute(
            text("UPDATE charts SET deleted_at = now() - INTERVAL '31 days' WHERE id = :cid"),
            {"cid": c.id},
        )
        await db_session.flush()
        with pytest.raises(ChartNotFound):
            await chart_service.restore(db_session, user, c.id)


@pytest.mark.asyncio
async def test_restore_at_cap_raises(db_session, user_and_dek):
    # 用户 plan=pro (cap=20)：cap 已满时 restore 软删的 chart 应抛 cap 错。
    # 原命名 "_at_15_cap_raises" 来自 plan 引入前的全局 15 上限。
    from app.db_types import user_dek_context
    from app.services import chart as chart_service
    from app.services.exceptions import ChartLimitExceeded
    user, dek = user_and_dek
    with user_dek_context(dek):
        victim = await _make_chart(db_session, user, label="victim")
        await chart_service.soft_delete(db_session, user, victim.id)
        # Fill up cap (20 for pro) active after the soft-delete
        for _ in range(20):
            await _make_chart(db_session, user)
        # Restore would make 21 active → 409
        with pytest.raises(ChartLimitExceeded):
            await chart_service.restore(db_session, user, victim.id)


@pytest.mark.asyncio
async def test_restore_wrong_owner_404(db_session, user_and_dek):
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
        await chart_service.soft_delete(db_session, user_a, c.id)
    with pytest.raises(ChartNotFound):
        await chart_service.restore(db_session, user_b, c.id)
