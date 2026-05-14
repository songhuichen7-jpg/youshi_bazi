"""chart_chips: history injection when conversation_id is provided. NOTE: spec §9."""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db_types import user_dek_context
from app.services import chart_chips
from app.services import conversation as conv_svc
from app.services import message as msg_svc


pytestmark = pytest.mark.asyncio


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
    from app.models.user import User
    dek = os.urandom(32)
    u = User(phone=f"+86138{uuid.uuid4().int % 10**8:08d}",
             dek_ciphertext=b"\x00" * 44)
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


async def test_stream_chips_loads_history_when_conversation_id_given(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    captured_history = {}

    def _fake_build(paipan, history=None):
        captured_history["value"] = list(history or [])
        return [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]

    async def _fake_stream(**kwargs):
        yield {"type": "model", "modelUsed": "fast"}
        yield {"type": "delta", "text": "[]"}
        yield {"type": "done", "tokens_used": 5}

    monkeypatch.setattr("app.services.chart_chips.build_messages", _fake_build)
    monkeypatch.setattr("app.services.chart_chips.chat_stream_with_fallback", _fake_stream)

    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()
        await msg_svc.insert(db_session, conversation_id=c.id, role="user", content="u1")
        await msg_svc.insert(db_session, conversation_id=c.id, role="assistant", content="a1")
        await db_session.flush()

        async for _ in chart_chips.stream_chips(
            db_session, user, chart, conversation_id=c.id,
        ):
            pass

    hist = captured_history["value"]
    assert [h["role"] for h in hist] == ["user", "assistant"]
    assert [h["content"] for h in hist] == ["u1", "a1"]


async def test_stream_chips_history_empty_when_conversation_id_none(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    captured_history = {}

    def _fake_build(paipan, history=None):
        captured_history["value"] = list(history or [])
        return [{"role": "system", "content": "x"}]

    async def _fake_stream(**kwargs):
        yield {"type": "model", "modelUsed": "fast"}
        yield {"type": "done", "tokens_used": 1}

    monkeypatch.setattr("app.services.chart_chips.build_messages", _fake_build)
    monkeypatch.setattr("app.services.chart_chips.chat_stream_with_fallback", _fake_stream)

    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        async for _ in chart_chips.stream_chips(
            db_session, user, chart, conversation_id=None,
        ):
            pass
    assert captured_history["value"] == []


async def test_stream_chips_disables_thinking_for_fast_followups(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    captured = {}

    def _fake_build(paipan, history=None):
        return [{"role": "system", "content": "x"}]

    async def _fake_stream(**kwargs):
        captured.update(kwargs)
        yield {"type": "model", "modelUsed": "fast"}
        yield {"type": "delta", "text": '["继续问什么"]'}
        yield {"type": "done", "tokens_used": 1}

    monkeypatch.setattr("app.services.chart_chips.build_messages", _fake_build)
    monkeypatch.setattr("app.services.chart_chips.chat_stream_with_fallback", _fake_stream)

    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        async for _ in chart_chips.stream_chips(db_session, user, chart):
            pass

    assert captured["tier"] == "fast"
    assert captured["disable_thinking"] is True
