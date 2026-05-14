"""services/message: insert + keyset pagination."""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db_types import user_dek_context
from app.services import conversation as conv_svc
from app.services import message as msg_svc


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures — copied per-file per repo convention (no conftest mutations)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Per-file chart helper
# ---------------------------------------------------------------------------


async def _make_chart(db_session, user, label=None):
    from app.db_types import user_dek_context
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service
    req = ChartCreateRequest(
        birth_input=BirthInput(year=1990, month=5, day=12, hour=12, gender="male"),
        label=label,
    )
    # Note: returns (chart, warnings) tuple
    return (await chart_service.create_chart(db_session, user, req))[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_insert_returns_row_with_id(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()
        m = await msg_svc.insert(db_session, conversation_id=c.id,
                                  role="user", content="hi")
        await db_session.commit()
        assert m.id is not None
        assert m.role == "user"
        assert m.content == "hi"


async def test_paginate_returns_newest_first(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()
        for i in range(5):
            await msg_svc.insert(db_session, conversation_id=c.id,
                                  role="user", content=f"m{i}")
            await db_session.commit()
            # Sleep 1ms so created_at strictly increases
            await asyncio.sleep(0.001)

        page = await msg_svc.paginate(db_session, conversation_id=c.id, before=None, limit=10)
        contents = [m.content for m in page["items"]]
        assert contents == ["m4", "m3", "m2", "m1", "m0"]
        assert page["next_cursor"] is None


async def test_paginate_cursor_keyset(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()
        ids = []
        for i in range(7):
            m = await msg_svc.insert(db_session, conversation_id=c.id,
                                      role="user", content=f"m{i}")
            await db_session.commit()
            ids.append(m.id)
            await asyncio.sleep(0.001)

        page1 = await msg_svc.paginate(db_session, conversation_id=c.id, before=None, limit=3)
        assert [m.content for m in page1["items"]] == ["m6", "m5", "m4"]
        # next_cursor = id of last item in page1 (m4 = ids[4]).
        # Pass it as `before` to get the next older page.
        assert page1["next_cursor"] == ids[4]

        page2 = await msg_svc.paginate(db_session, conversation_id=c.id,
                                        before=page1["next_cursor"], limit=3)
        assert [m.content for m in page2["items"]] == ["m3", "m2", "m1"]


async def test_paginate_limit_clamps(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()
        # Out of range → ValueError
        with pytest.raises(ValueError):
            await msg_svc.paginate(db_session, conversation_id=c.id, before=None, limit=0)
        with pytest.raises(ValueError):
            await msg_svc.paginate(db_session, conversation_id=c.id, before=None, limit=101)


async def test_recent_history_for_chat_returns_user_assistant_only(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()
        await msg_svc.insert(db_session, conversation_id=c.id, role="user", content="u1")
        await msg_svc.insert(db_session, conversation_id=c.id, role="assistant", content="a1")
        await msg_svc.insert(db_session, conversation_id=c.id, role="cta",
                              content=None, meta={"question": "?"})
        await msg_svc.insert(db_session, conversation_id=c.id, role="gua",
                              content=None, meta={})
        await msg_svc.insert(db_session, conversation_id=c.id, role="user", content="u2")
        await db_session.commit()

        hist = await msg_svc.recent_chat_history(db_session, conversation_id=c.id, limit=8)
        roles = [h["role"] for h in hist]
        contents = [h["content"] for h in hist]
        # Chronological order, user/assistant only
        assert roles == ["user", "assistant", "user"]
        assert contents == ["u1", "a1", "u2"]


async def test_delete_last_cta_removes_only_latest(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()
        await msg_svc.insert(db_session, conversation_id=c.id, role="cta",
                              content=None, meta={"question": "old"})
        await asyncio.sleep(0.001)
        cta2 = await msg_svc.insert(db_session, conversation_id=c.id, role="cta",
                                     content=None, meta={"question": "new"})
        await db_session.commit()

        deleted_id = await msg_svc.delete_last_cta(db_session, conversation_id=c.id)
        await db_session.commit()
        assert deleted_id == cta2.id

        # Second call returns None (only the older cta remains)
        rest = await msg_svc.paginate(db_session, conversation_id=c.id, before=None, limit=10)
        assert any(m.role == "cta" for m in rest["items"])


async def test_delete_last_cta_returns_none_when_no_cta(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()
        # Insert only user/assistant messages, no cta
        await msg_svc.insert(db_session, conversation_id=c.id, role="user", content="x")
        await db_session.flush()
        deleted = await msg_svc.delete_last_cta(db_session, conversation_id=c.id)
        assert deleted is None


async def test_recent_chat_history_respects_limit(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()
        for i in range(10):
            await msg_svc.insert(db_session, conversation_id=c.id,
                                  role="user", content=f"u{i}")
            await db_session.flush()
            await asyncio.sleep(0.001)
        hist = await msg_svc.recent_chat_history(db_session, conversation_id=c.id, limit=4)
        # Last 4 in chronological order: u6, u7, u8, u9
        assert [h["content"] for h in hist] == ["u6", "u7", "u8", "u9"]


async def test_context_chat_history_keeps_more_than_eight_when_budget_allows(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()
        for i in range(15):
            role = "user" if i % 2 == 0 else "assistant"
            await msg_svc.insert(db_session, conversation_id=c.id,
                                  role=role, content=f"m{i}")
            await db_session.flush()
            await asyncio.sleep(0.001)

        hist = await msg_svc.context_chat_history(
            db_session,
            conversation_id=c.id,
            max_messages=60,
            char_budget=10_000,
            always_keep=12,
        )

        assert len(hist) == 15
        assert [h["content"] for h in hist] == [f"m{i}" for i in range(15)]


async def test_context_chat_history_keeps_recent_tail_even_when_budget_is_tight(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()
        for i in range(10):
            await msg_svc.insert(
                db_session,
                conversation_id=c.id,
                role="user",
                content=f"long-{i}-" + ("x" * 120),
            )
            await db_session.flush()
            await asyncio.sleep(0.001)

        hist = await msg_svc.context_chat_history(
            db_session,
            conversation_id=c.id,
            max_messages=20,
            char_budget=50,
            always_keep=3,
        )

        assert [h["content"][:6] for h in hist] == ["long-7", "long-8", "long-9"]
