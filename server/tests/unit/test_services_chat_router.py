"""services/chat_router: LLM-first classify with keyword fallback on outage."""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services import chat_router as cr
from app.services.exceptions import UpstreamLLMError


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


async def test_keyword_match_still_uses_llm_router(monkeypatch, db_session, user_and_dek):
    user, _ = user_and_dek
    captured = {}

    async def _fake_llm(*, messages, tier, temperature, max_tokens, disable_thinking):
        captured["tier"] = tier
        captured["disable_thinking"] = disable_thinking
        captured["messages"] = messages
        return ('{"intent":"timing","reason":"LLM 判断为时间节点"}', "mimo-v2.5")

    monkeypatch.setattr("app.services.chat_router.chat_once_with_fallback", _fake_llm)
    async def _noop_log(*a, **kw):
        return None
    monkeypatch.setattr("app.services.chat_router.insert_llm_usage_log", _noop_log)

    out = await cr.classify(
        db=db_session, user=user, chart_id=uuid.uuid4(),
        message="接下来两年的关键节点", history=[],
    )
    assert out["intent"] == "timing"
    assert out["source"] == "llm"
    assert captured["tier"] == "fast"
    assert captured["disable_thinking"] is True


async def test_llm_fallback_when_no_keyword(monkeypatch, db_session, user_and_dek):
    user, _ = user_and_dek
    captured = {}

    async def _fake_llm(*, messages, tier, temperature, max_tokens, disable_thinking):
        captured["tier"] = tier
        captured["disable_thinking"] = disable_thinking
        return ('{"intent":"meta","reason":"问命理概念"}', "mimo-v2-fast")

    log_calls = []
    async def _capture_log(*a, **kw):
        log_calls.append(kw)

    monkeypatch.setattr("app.services.chat_router.chat_once_with_fallback", _fake_llm)
    monkeypatch.setattr("app.services.chat_router.insert_llm_usage_log", _capture_log)

    out = await cr.classify(
        db=db_session, user=user, chart_id=uuid.uuid4(),
        message="阐述一下子平真诠的中心思想", history=[],
    )
    assert out["intent"] == "meta"
    assert out["source"] == "llm"
    assert out["artifact"]["enabled"] is False
    assert captured["tier"] == "fast"
    assert captured["disable_thinking"] is True
    assert log_calls and log_calls[0]["endpoint"] == "chat:router"


async def test_llm_error_falls_back_to_keyword_when_possible(monkeypatch, db_session, user_and_dek):
    user, _ = user_and_dek

    async def _boom(*a, **kw):
        raise UpstreamLLMError(code="UPSTREAM_LLM_TIMEOUT", message="boom")

    monkeypatch.setattr("app.services.chat_router.chat_once_with_fallback", _boom)
    async def _noop_log(*a, **kw):
        return None
    monkeypatch.setattr("app.services.chat_router.insert_llm_usage_log", _noop_log)

    out = await cr.classify(
        db=db_session, user=user, chart_id=uuid.uuid4(),
        message="接下来两年的关键节点", history=[],
    )
    assert out["intent"] == "timing"
    assert out["source"] == "keyword_fallback"
    assert out["reason"].startswith("router_error;")


async def test_llm_error_without_keyword_falls_back_to_other(monkeypatch, db_session, user_and_dek):
    user, _ = user_and_dek

    async def _boom(*a, **kw):
        raise UpstreamLLMError(code="UPSTREAM_LLM_TIMEOUT", message="boom")

    monkeypatch.setattr("app.services.chat_router.chat_once_with_fallback", _boom)
    async def _noop_log(*a, **kw):
        return None
    monkeypatch.setattr("app.services.chat_router.insert_llm_usage_log", _noop_log)

    out = await cr.classify(
        db=db_session, user=user, chart_id=uuid.uuid4(),
        message="please describe my chart in english", history=[],
    )
    assert out["intent"] == "other"
    assert out["reason"] == "router_error"
    assert out["source"] == "llm_error"
