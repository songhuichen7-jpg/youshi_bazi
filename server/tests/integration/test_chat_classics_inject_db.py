"""maybe_classics_segment — cache read behavior.

Cache miss → "". Cache hit with persona → formatted segment.
Cache hit but persona null → "". Corrupt JSON → "".
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.crypto import decrypt_dek, load_kek
from app.db_types import user_dek_context
from app.models.chart import ChartCache
from app.models.user import User
from app.services.chat_classics_inject import maybe_classics_segment
from tests.integration.conftest import register_user

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db_session(client, database_url):
    """Committing AsyncSession bound to the test container DB.

    Depends on ``client`` to ensure env + app state is set up first. Uses a
    fresh engine so writes are visible across the FastAPI request boundary
    (which commits via its own engine)."""
    engine = create_async_engine(str(database_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _make_chart(client, cookie):
    body = {
        "birth_input": {
            "year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male",
        },
    }
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    assert r.status_code == 201, r.text
    return r.json()["chart"]["id"]


async def _seed_cache(db_session, chart_id, content):
    # Read the current cache version from classics_polisher — single source
    # of truth, so this test doesn't drift each time we bump v11→v12→…
    from app.services.classics_polisher import CLASSICS_CACHE_VERSION
    db_session.add(ChartCache(
        chart_id=chart_id, kind="classics", key=CLASSICS_CACHE_VERSION,
        content=content, model_used=None, tokens_used=None,
    ))
    await db_session.commit()


async def _register(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    return await register_user(client, phone)


async def _user_dek(db_session, user_id) -> bytes:
    """Fetch + decrypt the user's DEK so we can read/write encrypted columns."""
    row = (await db_session.execute(
        select(User).where(User.id == uuid.UUID(user_id)),
    )).scalar_one()
    return decrypt_dek(row.dek_ciphertext, load_kek())


async def test_cache_miss_returns_empty(db_session, client):
    cookie, user = await _register(client)
    chart_id_str = await _make_chart(client, cookie)
    chart_id = uuid.UUID(chart_id_str)
    dek = await _user_dek(db_session, user["id"])

    with user_dek_context(dek):
        out = await maybe_classics_segment(db_session, chart_id)
    assert out == ""


async def test_cache_hit_with_persona_returns_formatted(db_session, client):
    cookie, user = await _register(client)
    chart_id_str = await _make_chart(client, cookie)
    chart_id = uuid.UUID(chart_id_str)
    dek = await _user_dek(db_session, user["id"])

    payload = json.dumps({
        "persona": {
            "quote": "甲子日元，生于孟春。",
            "plain": "木火得位。",
            "book": "滴天髓", "chapter": "性情",
            "tier": "case", "fit_note": "日干甲、月令寅。",
        },
        "verdict": None,
    })
    with user_dek_context(dek):
        await _seed_cache(db_session, chart_id, payload)
        out = await maybe_classics_segment(db_session, chart_id)
    assert "古书定调" in out
    assert "甲子日元" in out
    assert "古人定语" not in out


async def test_cache_hit_with_persona_null_returns_empty(db_session, client):
    cookie, user = await _register(client)
    chart_id_str = await _make_chart(client, cookie)
    chart_id = uuid.UUID(chart_id_str)
    dek = await _user_dek(db_session, user["id"])

    with user_dek_context(dek):
        await _seed_cache(
            db_session, chart_id, json.dumps({"persona": None, "verdict": None}),
        )
        out = await maybe_classics_segment(db_session, chart_id)
    assert out == ""


async def test_corrupt_json_returns_empty(db_session, client):
    cookie, user = await _register(client)
    chart_id_str = await _make_chart(client, cookie)
    chart_id = uuid.UUID(chart_id_str)
    dek = await _user_dek(db_session, user["id"])

    with user_dek_context(dek):
        await _seed_cache(db_session, chart_id, "{ this is not json")
        out = await maybe_classics_segment(db_session, chart_id)
    assert out == ""
