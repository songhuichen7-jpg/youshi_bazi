"""services/conversation: CRUD + ownership + soft-delete/restore."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db_types import user_dek_context
from app.services import conversation as conv_svc
from app.services.exceptions import (
    ConversationAlreadyDeletedError,
    ConversationGoneError,
    NotFoundError,
)


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


async def test_list_conversations_returns_only_active_for_owner(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c1 = await conv_svc.create_conversation(db_session, user, chart.id, label="对话 1")
        c2 = await conv_svc.create_conversation(db_session, user, chart.id, label="对话 2")
        await db_session.commit()

        rows = await conv_svc.list_conversations(db_session, user, chart.id)
        ids = [r.id for r in rows]
        assert c1.id in ids and c2.id in ids

        await conv_svc.soft_delete(db_session, user, c1.id)
        await db_session.commit()
        rows2 = await conv_svc.list_conversations(db_session, user, chart.id)
        assert c1.id not in [r.id for r in rows2]
        assert c2.id in [r.id for r in rows2]


async def test_get_conversation_cross_user_404(db_session, user_and_dek):
    user, dek = user_and_dek
    # Second user — created inline, mirror test_list_charts_isolated_per_user
    from app.models.user import User
    user_b = User(
        phone=f"+86139{uuid.uuid4().int % 10**8:08d}",
        dek_ciphertext=b"\x00" * 44,
    )
    db_session.add(user_b)
    await db_session.flush()
    dek_b = os.urandom(32)

    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()

    with user_dek_context(dek_b):
        with pytest.raises(NotFoundError):
            await conv_svc.get_conversation(db_session, user_b, c.id)


async def test_create_assigns_increasing_position(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c1 = await conv_svc.create_conversation(db_session, user, chart.id)
        c2 = await conv_svc.create_conversation(db_session, user, chart.id)
        c3 = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()
        assert c1.position == 0
        assert c2.position == 1
        assert c3.position == 2


async def test_patch_label_updates(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id, label="old")
        await db_session.commit()
        updated = await conv_svc.patch_label(db_session, user, c.id, "new")
        await db_session.commit()
        assert updated.label == "new"


async def test_soft_delete_then_restore_within_30d(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()
        await conv_svc.soft_delete(db_session, user, c.id)
        await db_session.commit()
        restored = await conv_svc.restore(db_session, user, c.id)
        await db_session.commit()
        assert restored.deleted_at is None


async def test_restore_outside_30d_raises_gone(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()
        # Manually backdate deleted_at past 30 days
        old = datetime.now(tz=timezone.utc) - timedelta(days=31)
        await db_session.execute(
            text("UPDATE conversations SET deleted_at = :d WHERE id = :id"),
            {"d": old, "id": c.id},
        )
        await db_session.commit()
        with pytest.raises(ConversationGoneError):
            await conv_svc.restore(db_session, user, c.id)


async def test_get_returns_message_count_and_last_message_at(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.commit()
        # No messages
        d = await conv_svc.get_conversation(db_session, user, c.id)
        assert d.message_count == 0
        assert d.last_message_at is None

        # Add 3 messages
        from app.services import message as msg_svc
        await msg_svc.insert(db_session, conversation_id=c.id, role="user", content="a")
        await msg_svc.insert(db_session, conversation_id=c.id, role="assistant", content="b")
        await msg_svc.insert(db_session, conversation_id=c.id, role="gua", content=None,
                              meta={"gua": {}})
        await db_session.commit()

        d2 = await conv_svc.get_conversation(db_session, user, c.id)
        assert d2.message_count == 3
        assert d2.last_message_at is not None


async def test_list_conversations_uses_single_aggregation_query(db_session, user_and_dek):
    """N+1 regression guard: list_conversations must run ≤ 3 queries
    (1 chart fetch + 1 list-with-aggregation join), regardless of conv count."""
    from sqlalchemy import event
    from app.db_types import user_dek_context
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        # Create 5 conversations + a few messages each
        from app.services import message as msg_svc
        for _ in range(5):
            conv = await conv_svc.create_conversation(db_session, user, chart.id)
            await msg_svc.insert(db_session, conversation_id=conv.id,
                                  role="user", content="x")
        await db_session.flush()

        bind = db_session.bind
        sync_engine = bind.sync_engine if hasattr(bind, "sync_engine") else bind
        count = {"n": 0}

        def _on_execute(*_a, **_kw):
            count["n"] += 1

        event.listen(sync_engine, "before_cursor_execute", _on_execute)
        try:
            rows = await conv_svc.list_conversations(db_session, user, chart.id)
        finally:
            event.remove(sync_engine, "before_cursor_execute", _on_execute)

        assert len(rows) == 5
        # Should be ≤ 3: owned-chart lookup + the aggregation query (+ tx mechanics)
        assert count["n"] <= 3, f"N+1 regression: {count['n']} queries issued"


async def test_soft_delete_twice_raises_already_deleted(db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()
        await conv_svc.soft_delete(db_session, user, c.id)
        await db_session.flush()
        with pytest.raises(ConversationAlreadyDeletedError):
            await conv_svc.soft_delete(db_session, user, c.id)
