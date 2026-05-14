"""conversation_memory: rolling long-term summaries for chat context."""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db_types import user_dek_context
from app.services import conversation as conv_svc
from app.services import conversation_memory as memory_svc
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
    u = User(
        phone=f"+86138{uuid.uuid4().int % 10**8:08d}",
        dek_ciphertext=b"\x00" * 44,
    )
    db_session.add(u)
    await db_session.flush()
    return u, dek


async def _make_chart(db_session, user):
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service
    req = ChartCreateRequest(
        birth_input=BirthInput(year=1990, month=5, day=12, hour=12, gender="male"),
        label="记忆测试",
    )
    return (await chart_service.create_chart(db_session, user, req))[0]


async def test_get_summary_returns_none_when_missing(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        assert await memory_svc.get_summary(db_session, conversation_id=c.id) is None


async def test_maybe_refresh_summary_summarizes_only_older_messages(
    monkeypatch, db_session, user_and_dek,
):
    user, dek = user_and_dek
    captured = {}

    async def _fake_chat_once(**kwargs):
        captured.update(kwargs)
        return "用户一直在追问七杀格、丁火用神，以及古籍旁证是否贴盘。", "fake-summary-model"

    monkeypatch.setattr("app.services.conversation_memory.chat_once_with_fallback", _fake_chat_once)

    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()
        for i in range(10):
            await msg_svc.insert(db_session, conversation_id=c.id, role="user", content=f"m{i}")
            await db_session.flush()
            await asyncio.sleep(0.001)

        refreshed = await memory_svc.maybe_refresh_summary(
            db_session,
            user=user,
            chart=chart,
            conversation_id=c.id,
            recent_keep=4,
            min_new_messages=1,
        )

        assert refreshed is True
        summary = await memory_svc.get_summary(db_session, conversation_id=c.id)
        assert "七杀格" in summary

    prompt_text = "\n\n".join(m["content"] for m in captured["messages"])
    assert "m0" in prompt_text
    assert "m5" in prompt_text
    assert "m6" not in prompt_text
    assert "m9" not in prompt_text
    assert captured["tier"] == "fast"
    assert captured["max_tokens"] >= 1200


async def test_maybe_refresh_summary_waits_until_enough_messages(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()
        for i in range(4):
            await msg_svc.insert(db_session, conversation_id=c.id, role="user", content=f"m{i}")
            await db_session.flush()

        refreshed = await memory_svc.maybe_refresh_summary(
            db_session,
            user=user,
            chart=chart,
            conversation_id=c.id,
            recent_keep=4,
            min_new_messages=1,
        )

        assert refreshed is False
        assert await memory_svc.get_summary(db_session, conversation_id=c.id) is None
