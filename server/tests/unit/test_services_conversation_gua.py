"""services/conversation_gua: cast + LLM SSE generator + cta consume."""
from __future__ import annotations

import json
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db_types import user_dek_context
from app.services import conversation as conv_svc
from app.services import conversation_gua as cg
from app.services import message as msg_svc
from app.services.exceptions import UpstreamLLMError
from app.services.quota import QuotaTicket


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


async def _consume(gen) -> list[dict]:
    out = []
    async for raw in gen:
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        for chunk in line.split("\n\n"):
            chunk = chunk.strip()
            if chunk.startswith("data: "):
                out.append(json.loads(chunk[len("data: "):]))
    return out


def _fake_stream_factory(deltas, model="mimo-v2-pro"):
    async def _f(**kwargs):
        yield {"type": "model", "modelUsed": model}
        for d in deltas:
            yield {"type": "delta", "text": d}
        yield {"type": "done", "tokens_used": 100,
               "prompt_tokens": 30, "completion_tokens": 70}
    return _f


async def test_gua_happy_path_writes_role_gua_message(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        monkeypatch.setattr("app.services.conversation_gua.chat_stream_with_fallback",
                             _fake_stream_factory(["§卦象\n", "雷"]))

        ticket = QuotaTicket(user=user, kind="gua", limit=20, _db=db_session)
        events = await _consume(cg.stream_gua(
            db=db_session, user=user, conversation_id=c.id, chart=chart,
            question="该不该跳槽", ticket=ticket,
        ))
        await db_session.flush()

        types = [e["type"] for e in events]
        assert types[0] == "gua"
        assert "model" in types and "delta" in types
        assert types[-1] == "done"

        page = await msg_svc.paginate(db_session, conversation_id=c.id,
                                       before=None, limit=10)
        roles = [m.role for m in page["items"]]
        assert roles == ["gua"]
        gua_msg = page["items"][0]
        assert gua_msg.content is None
        assert "gua" in gua_msg.meta and "question" in gua_msg.meta
        assert gua_msg.meta["question"] == "该不该跳槽"


async def test_gua_consumes_existing_cta(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()
        await msg_svc.insert(db_session, conversation_id=c.id, role="user", content="该不该 X")
        await msg_svc.insert(db_session, conversation_id=c.id, role="cta",
                              content=None, meta={"question": "该不该 X"})
        await db_session.flush()

        monkeypatch.setattr("app.services.conversation_gua.chat_stream_with_fallback",
                             _fake_stream_factory(["占算"]))

        ticket = QuotaTicket(user=user, kind="gua", limit=20, _db=db_session)
        events = await _consume(cg.stream_gua(
            db=db_session, user=user, conversation_id=c.id, chart=chart,
            question="该不该 X", ticket=ticket,
        ))
        await db_session.flush()

        page = await msg_svc.paginate(db_session, conversation_id=c.id,
                                       before=None, limit=10)
        roles = [m.role for m in page["items"]]
        assert roles == ["gua", "user"]


async def test_gua_llm_error_writes_no_message(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        async def _boom(**kwargs):
            yield {"type": "model", "modelUsed": "mimo-v2-pro"}
            raise UpstreamLLMError(code="UPSTREAM_LLM_TIMEOUT", message="boom")

        monkeypatch.setattr("app.services.conversation_gua.chat_stream_with_fallback", _boom)

        ticket = QuotaTicket(user=user, kind="gua", limit=20, _db=db_session)
        events = await _consume(cg.stream_gua(
            db=db_session, user=user, conversation_id=c.id, chart=chart,
            question="?", ticket=ticket,
        ))
        await db_session.flush()

        types = [e["type"] for e in events]
        assert types[-1] == "error"
        page = await msg_svc.paginate(db_session, conversation_id=c.id,
                                       before=None, limit=10)
        assert page["items"] == []
        assert not ticket._committed


# ---------------------------------------------------------------------------
# Pure-function unit tests for _derive_birth_context
# ---------------------------------------------------------------------------

def test_derive_birth_context_handles_none():
    from app.services.conversation_gua import _derive_birth_context
    assert _derive_birth_context(None) == {
        "rizhu": None, "currentDayun": None, "currentYear": None,
    }
    assert _derive_birth_context({}) == {
        "rizhu": None, "currentDayun": None, "currentYear": None,
    }


def test_derive_birth_context_dayun_dict_shape():
    from app.services.conversation_gua import _derive_birth_context
    paipan = {
        "rizhu": "丙",
        "todayYmd": "2026-04-18",
        "todayYearGz": "丙午",
        "dayun": {"list": [
            {"ganZhi": "戊辰", "startYear": 2015, "endYear": 2024},
            {"ganZhi": "己巳", "startYear": 2025, "endYear": 2034},
        ]},
    }
    assert _derive_birth_context(paipan) == {
        "rizhu": "丙",
        "currentDayun": "己巳",
        "currentYear": "丙午",
    }


def test_derive_birth_context_dayun_plain_list_shape():
    from app.services.conversation_gua import _derive_birth_context
    paipan = {
        "rizhu": "丙",
        "todayYmd": "2026-04-18",
        "todayYearGz": "丙午",
        "dayun": [
            {"ganZhi": "戊辰", "startYear": 2015, "endYear": 2024},
            {"ganZhi": "己巳", "startYear": 2025, "endYear": 2034},
        ],
    }
    assert _derive_birth_context(paipan)["currentDayun"] == "己巳"


def test_derive_birth_context_no_dayun_match():
    """today_year=2026 outside all dayun ranges → currentDayun stays None."""
    from app.services.conversation_gua import _derive_birth_context
    paipan = {
        "rizhu": "丙",
        "todayYmd": "2026-04-18",
        "todayYearGz": "丙午",
        "dayun": {"list": [
            {"ganZhi": "戊辰", "startYear": 1990, "endYear": 1999},
        ]},
    }
    out = _derive_birth_context(paipan)
    assert out["currentDayun"] is None
    assert out["currentYear"] == "丙午"  # year_gz still extracted from todayYearGz


def test_derive_birth_context_ganzhi_key_priority():
    """Step uses 'ganzhi' (lowercase z) instead of 'ganZhi' — picked up via fallback."""
    from app.services.conversation_gua import _derive_birth_context
    paipan = {
        "rizhu": "丙", "todayYmd": "2026-04-18", "todayYearGz": "丙午",
        "dayun": {"list": [
            {"ganzhi": "己巳", "startYear": 2025, "endYear": 2034},
        ]},
    }
    assert _derive_birth_context(paipan)["currentDayun"] == "己巳"
