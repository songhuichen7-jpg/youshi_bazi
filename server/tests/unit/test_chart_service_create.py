"""chart service — create_chart: paipan wiring, encrypted roundtrip, 15-cap."""
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
    """Create a fresh user with a real random DEK; yield (user, dek).

    NOTE: 钉到 pro 档位（chart_max=20）— 这一组测试目的是验"命盘上限的
    enforcement 行为"，需要造大于 1-2 张的 chart。lite 档位 chart_max=2，
    第 3 张就会撞上限，把 limit-enforcement 测试本身变成 limit-overflow
    测试。pro 档给 20 张余量足够测各类边界。
    """
    from app.models.user import User
    dek = os.urandom(32)
    u = User(
        phone=f"+86138{uuid.uuid4().int % 10**8:08d}",
        dek_ciphertext=b"\x00" * 44,  # placeholder; service uses contextvar not this
        plan="pro",
    )
    db_session.add(u)
    await db_session.flush()
    return u, dek


@pytest.mark.asyncio
async def test_create_chart_happy_path(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service
    import paipan

    user, dek = user_and_dek
    req = ChartCreateRequest(
        birth_input=BirthInput(
            year=1990, month=5, day=12, hour=14, minute=30,
            city="北京", gender="male",
        ),
        label="测试盘",
    )
    with user_dek_context(dek):
        created, warnings = await chart_service.create_chart(db_session, user, req)

    assert created.user_id == user.id
    assert created.label == "测试盘"
    assert created.engine_version == paipan.VERSION
    assert created.deleted_at is None
    # paipan dict roundtrips through EncryptedJSONB
    assert "sizhu" in created.paipan
    assert isinstance(warnings, list)


@pytest.mark.asyncio
async def test_create_chart_label_optional(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service

    user, dek = user_and_dek
    req = ChartCreateRequest(
        birth_input=BirthInput(year=1990, month=5, day=12, hour=12, gender="male"),
    )
    with user_dek_context(dek):
        created, _ = await chart_service.create_chart(db_session, user, req)
    assert created.label is None


@pytest.mark.asyncio
async def test_create_chart_city_canonicalized_writeback(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service

    user, dek = user_and_dek
    req = ChartCreateRequest(
        birth_input=BirthInput(year=1990, month=5, day=12, hour=14,
                               city="北京市", gender="male"),  # 带"市"
    )
    with user_dek_context(dek):
        created, _ = await chart_service.create_chart(db_session, user, req)
    # DB stored birth_input.city must match what get_city_coords canonicalizes.
    # NOTE: the canonical form depends on cities-data.json; don't hardcode
    # "北京" vs "北京市" — ask paipan.
    from paipan.cities import get_city_coords
    expected = get_city_coords("北京市").canonical
    assert created.birth_input["city"] == expected


@pytest.mark.asyncio
async def test_create_chart_unknown_city_kept_verbatim_with_warning(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service

    user, dek = user_and_dek
    req = ChartCreateRequest(
        birth_input=BirthInput(year=1990, month=5, day=12, hour=14,
                               city="ZZZZ未知城市", gender="male"),
    )
    with user_dek_context(dek):
        created, warnings = await chart_service.create_chart(db_session, user, req)
    assert created.birth_input["city"] == "ZZZZ未知城市"  # 原样保留
    assert any("未识别城市" in w for w in warnings)


@pytest.mark.asyncio
async def test_create_chart_hour_unknown(db_session, user_and_dek):
    from app.db_types import user_dek_context
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service

    user, dek = user_and_dek
    req = ChartCreateRequest(
        birth_input=BirthInput(year=1990, month=5, day=12, hour=-1, gender="female"),
    )
    with user_dek_context(dek):
        created, _ = await chart_service.create_chart(db_session, user, req)
    assert created.paipan["hourUnknown"] is True
    assert created.birth_input["hour"] == -1


@pytest.mark.asyncio
async def test_create_chart_over_cap_raises_limit(db_session, user_and_dek):
    # 用户 plan=pro，chart_max=20。造满 20 张后第 21 张应抛 ChartLimitExceeded
    # 并带 limit=20。原测试名/范围（"16th"/15 张）来自 plan 引入前的全局
    # 15 上限——已经废弃。
    from app.db_types import user_dek_context
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service
    from app.services.exceptions import ChartLimitExceeded

    user, dek = user_and_dek
    req = ChartCreateRequest(
        birth_input=BirthInput(year=1990, month=5, day=12, hour=12, gender="male"),
    )
    with user_dek_context(dek):
        for _ in range(20):
            await chart_service.create_chart(db_session, user, req)
        with pytest.raises(ChartLimitExceeded) as exc:
            await chart_service.create_chart(db_session, user, req)
    assert exc.value.details == {"limit": 20}


@pytest.mark.asyncio
async def test_create_chart_soft_deleted_not_counted(db_session, user_and_dek):
    # 软删的 chart 不计入 cap — 验在 cap 顶端发生 1 软删之后，新建仍能成功。
    # 用户 plan=pro (cap=20)：造 20 张到顶 → 软删 1 → 第 21 次创建应该过
    # （活跃数 19 + 1 新 = 20，没超 cap）。
    from app.db_types import user_dek_context
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service
    from sqlalchemy import text

    user, dek = user_and_dek
    req = ChartCreateRequest(
        birth_input=BirthInput(year=1990, month=5, day=12, hour=12, gender="male"),
    )
    with user_dek_context(dek):
        for _ in range(20):
            await chart_service.create_chart(db_session, user, req)
        # NOTE: Postgres doesn't support UPDATE ... LIMIT; use a CTE.
        await db_session.execute(
            text("""
                UPDATE charts SET deleted_at = now()
                 WHERE id = (SELECT id FROM charts
                              WHERE user_id = :uid AND deleted_at IS NULL
                              LIMIT 1)
            """),
            {"uid": user.id},
        )
        await db_session.flush()
        created, _ = await chart_service.create_chart(db_session, user, req)
    assert created.deleted_at is None
