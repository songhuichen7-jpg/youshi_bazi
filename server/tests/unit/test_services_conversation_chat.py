"""services/conversation_chat: orchestrator (Stage 1+2 + persistence + quota)."""
from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db_types import user_dek_context
from app.services import conversation as conv_svc
from app.services import conversation_chat as cc
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


async def _make_chart(db_session, user, label=None, birth_updates=None):
    from app.schemas.chart import BirthInput, ChartCreateRequest
    from app.services import chart as chart_service
    birth_data = {
        "year": 1990,
        "month": 5,
        "day": 12,
        "hour": 12,
        "gender": "male",
    }
    if birth_updates:
        birth_data.update(birth_updates)
    req = ChartCreateRequest(
        birth_input=BirthInput(**birth_data),
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


def _fake_classify(intent="other", reason="ok", source="keyword"):
    async def _f(**_):
        return {"intent": intent, "reason": reason, "source": source}
    return _f


def _fake_stream_factory(deltas, tokens=42, model="mimo-v2-pro"):
    async def _f(**kwargs):
        yield {"type": "model", "modelUsed": model}
        for d in deltas:
            yield {"type": "delta", "text": d}
        yield {"type": "done", "tokens_used": tokens,
               "prompt_tokens": tokens // 3,
               "completion_tokens": tokens - tokens // 3}
    return _f


def _fake_stream_factory_error(err):
    async def _f(**kwargs):
        yield {"type": "model", "modelUsed": "mimo-v2-pro"}
        raise err
        yield  # noqa
    return _f


def _tiny_paipan(*, day: str, gender: str, year: int, city: str) -> dict:
    return {
        "sizhu": {"year": "癸未", "month": "庚申", "day": day, "hour": "戊辰"},
        "rizhu": day[0],
        "gender": gender,
        "birthInput": {
            "year": year,
            "month": 8,
            "day": 29,
            "hour": 8,
            "minute": 25,
            "city": city,
            "gender": gender,
            "useTrueSolarTime": True,
            "ziConvention": "early",
        },
        "shishen": {"year": "正印", "month": "七杀", "day": "日主", "hour": "偏财"},
        "cangGan": {
            "year": [{"gan": "己", "shiShen": "正财"}],
            "month": [{"gan": "庚", "shiShen": "七杀"}],
            "day": [{"gan": day[1], "shiShen": "偏财"}],
            "hour": [{"gan": "戊", "shiShen": "偏财"}],
        },
        "naYin": {"year": "杨柳木", "month": "石榴木", "day": "山头火", "hour": "大林木"},
        "dayun": [{"ganzhi": "戊午", "shishen": "偏财", "startAge": 18}],
        "todayYmd": "2026-05-07",
        "todayYearGz": "丙午",
    }


async def test_normal_flow_writes_user_then_assistant(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    stream_kwargs = {}
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        monkeypatch.setattr("app.services.conversation_chat.classify",
                             _fake_classify(intent="career", source="keyword"))
        async def _fake_stream(**kwargs):
            stream_kwargs.update(kwargs)
            async for ev in _fake_stream_factory(["你好", "世界"])(**kwargs):
                yield ev
        monkeypatch.setattr("app.services.conversation_chat.chat_stream_with_fallback", _fake_stream)
        async def _no_retr(*a, **kw):
            return []
        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart", _no_retr)
        monkeypatch.setattr("app.services.conversation_chat.compose_retrieval3", _no_retr)

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        events = await _consume(cc.stream_message(
            db=db_session, user=user, conversation_id=c.id,
            chart=chart, message="我想换工作", bypass_divination=False,
            ticket=ticket,
        ))
        await db_session.flush()

        types = [e["type"] for e in events]
        assert types[0] == "intent"
        assert "model" in types and "delta" in types
        assert types[-1] == "done"

        page = await msg_svc.paginate(db_session, conversation_id=c.id,
                                       before=None, limit=10)
        roles = [m.role for m in page["items"]]
        assert roles == ["assistant", "user"]
        assert page["items"][0].content == "你好世界"
        # max_tokens 在 10000-15000 区间——thinking 模型把 reasoning_tokens 算进
        # completion_tokens，需要给 thinking 6000-8000 + 可见输出 4000-6000。详见
        # commit f243e22 "max_tokens 拉到 12000"。
        assert 10000 <= stream_kwargs["max_tokens"] <= 15000
        system_prompt = stream_kwargs["messages"][0]["content"]
        assert "性别  男命" in system_prompt


async def test_normal_flow_injects_birth_place_and_corrected_time(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    stream_kwargs = {}
    retrieval_chart = {}
    with user_dek_context(dek):
        chart = await _make_chart(
            db_session,
            user,
            birth_updates={
                "hour": 14,
                "minute": 30,
                "city": "北京",
                "longitude": 116.407526,
                "gender": "female",
                "useTrueSolarTime": True,
                "ziConvention": "early",
            },
        )
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        monkeypatch.setattr(
            "app.services.conversation_chat.classify",
            _fake_classify(intent="relationship", source="llm"),
        )

        async def _fake_stream(**kwargs):
            stream_kwargs.update(kwargs)
            async for ev in _fake_stream_factory(["好"])(**kwargs):
                yield ev

        monkeypatch.setattr("app.services.conversation_chat.chat_stream_with_fallback", _fake_stream)

        async def _no_retr(paipan, *a, **kw):
            retrieval_chart.update(paipan)
            return []

        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart", _no_retr)
        monkeypatch.setattr("app.services.conversation_chat.compose_retrieval3", _no_retr)

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        await _consume(cc.stream_message(
            db=db_session,
            user=user,
            conversation_id=c.id,
            chart=chart,
            message="我的正缘怎么样",
            bypass_divination=False,
            ticket=ticket,
        ))

        system_prompt = stream_kwargs["messages"][0]["content"]
        assert "性别  女命" in system_prompt
        assert "出生资料" in system_prompt
        assert "公历:1990-05-12 14:30" in system_prompt
        assert "出生地:北京" in system_prompt
        assert "经度:116.407526" in system_prompt
        assert "真太阳时:开启" in system_prompt
        assert "子初换日:早子" in system_prompt
        assert "校正后:" in system_prompt
        assert "农历:" in system_prompt
        assert retrieval_chart["birthInput"]["city"] == "北京"
        assert retrieval_chart["birthInput"]["gender"] == "female"


async def test_followup_cue_still_uses_llm_router(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        async def _old_intent(*_a, **_kw):
            return "personality"

        classify_calls = []

        async def _classify(**kwargs):
            classify_calls.append(kwargs)
            return {"intent": "timing", "reason": "LLM 判断为追问时间线", "source": "llm"}

        monkeypatch.setattr(
            "app.services.conversation_chat.msg_svc.latest_assistant_intent",
            _old_intent,
        )
        monkeypatch.setattr("app.services.conversation_chat.classify", _classify)
        monkeypatch.setattr(
            "app.services.conversation_chat.chat_stream_with_fallback",
            _fake_stream_factory(["好的"]),
        )

        async def _no_retr(*a, **kw):
            return []

        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart", _no_retr)
        monkeypatch.setattr("app.services.conversation_chat.compose_retrieval3", _no_retr)

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        events = await _consume(cc.stream_message(
            db=db_session, user=user, conversation_id=c.id,
            chart=chart, message="继续展开一下", bypass_divination=False,
            ticket=ticket,
        ))

        assert classify_calls
        assert events[0]["type"] == "intent"
        assert events[0]["intent"] == "timing"
        assert events[0]["source"] == "llm"


async def test_user_message_commits_before_long_llm_stream(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    commit_count = 0
    real_commit = db_session.commit

    async def _commit_spy():
        nonlocal commit_count
        commit_count += 1
        await real_commit()

    monkeypatch.setattr(db_session, "commit", _commit_spy)

    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        monkeypatch.setattr(
            "app.services.conversation_chat.classify",
            _fake_classify(intent="career", source="llm"),
        )

        commit_count_at_stream_start = []

        async def _fake_stream(**kwargs):
            commit_count_at_stream_start.append(commit_count)
            async for ev in _fake_stream_factory(["半截", "回答"])(**kwargs):
                yield ev

        monkeypatch.setattr("app.services.conversation_chat.chat_stream_with_fallback", _fake_stream)

        async def _no_retr(*a, **kw):
            return []

        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart", _no_retr)
        monkeypatch.setattr("app.services.conversation_chat.compose_retrieval3", _no_retr)

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        await _consume(cc.stream_message(
            db=db_session, user=user, conversation_id=c.id,
            chart=chart, message="问问事业", bypass_divination=False,
            ticket=ticket,
        ))

        assert commit_count_at_stream_start == [1]


async def test_cancelled_stream_persists_interrupted_partial_answer(
    monkeypatch, db_session, user_and_dek
):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        monkeypatch.setattr(
            "app.services.conversation_chat.classify",
            _fake_classify(intent="career", source="llm"),
        )

        async def _cancel_after_delta(**_kwargs):
            yield {"type": "model", "modelUsed": "mimo-v2-pro"}
            yield {"type": "delta", "text": "半截回答"}
            raise asyncio.CancelledError()

        monkeypatch.setattr(
            "app.services.conversation_chat.chat_stream_with_fallback",
            _cancel_after_delta,
        )

        async def _no_retr(*a, **kw):
            return []

        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart", _no_retr)
        monkeypatch.setattr("app.services.conversation_chat.compose_retrieval3", _no_retr)

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        with pytest.raises(asyncio.CancelledError):
            await _consume(cc.stream_message(
                db=db_session, user=user, conversation_id=c.id,
                chart=chart, message="问问事业", bypass_divination=False,
                ticket=ticket,
            ))

        page = await msg_svc.paginate(db_session, conversation_id=c.id, before=None, limit=10)
        roles = [m.role for m in page["items"]]
        assert roles == ["assistant", "user"]
        assert page["items"][0].content == "半截回答"
        assert page["items"][0].meta["interrupted"] is True
        assert not ticket._committed


async def test_planner_can_request_classics_for_media_intent(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    retrieve_calls = []
    stream_kwargs = {}
    route_plan = {
        "intent": "media",
        "reason": "用户要电影类比，但需要命理依据",
        "source": "llm",
        "secondary_intents": ["personality"],
        "needs": {
            "chart": True,
            "classics": True,
            "memory": True,
            "hepan": True,
            "divination": False,
        },
        "retrieval_plan": {
            "enabled": True,
            "focus": ["性情", "情绪模式", "五行刚柔"],
            "reason": "先找性情依据再类比电影",
        },
        "artifact": {
            "enabled": True,
            "kind": "movie",
            "reason": "用户明确要求电影",
        },
        "answer_plan": {
            "format": "core_then_bullets",
            "style": "先讲结构，再给电影卡片",
            "should_clarify": False,
        },
    }

    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        async def _classify(**_kwargs):
            return route_plan

        async def _retrieve(chart_arg, kind, user_message=None, **kwargs):
            retrieve_calls.append({
                "kind": kind,
                "user_message": user_message,
                "kwargs": kwargs,
            })
            return [{"source": "滴天髓 · 性情", "file": "x.md", "scope": "full", "text": "性情原文", "chars": 4}]

        async def _retrieve_compound(chart_arg, kinds, user_message=None, **kwargs):
            retrieve_calls.append({
                "kind": list(kinds),
                "user_message": user_message,
                "kwargs": kwargs,
            })
            return [{"source": "滴天髓 · 性情", "file": "x.md", "scope": "full", "text": "性情原文", "chars": 4}]

        # 现在 conversation_chat 走 retrieval3 composer; 这里 mock composer
        # 接收 (chart, intent, secondary_intents, user_message, retrieval_focus)
        # 全部 kwargs 形态,记录到 retrieve_calls 供断言。
        async def _compose(chart_arg, *, intent, secondary_intents=None,
                           user_message=None, retrieval_focus=None, **kwargs):
            retrieve_calls.append({
                "intent": intent,
                "secondary_intents": list(secondary_intents or []),
                "user_message": user_message,
                "retrieval_focus": list(retrieval_focus or []),
            })
            return [{"source": "滴天髓 · 性情", "file": "x.md", "scope": "full",
                     "text": "性情原文", "chars": 4}]

        monkeypatch.setattr("app.services.conversation_chat.classify", _classify)
        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart", _retrieve)
        monkeypatch.setattr("app.services.conversation_chat.compose_retrieval3", _compose)
        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart_compound", _retrieve_compound)
        async def _fake_stream(**kwargs):
            stream_kwargs.update(kwargs)
            async for ev in _fake_stream_factory(["像", "电影"])(**kwargs):
                yield ev

        monkeypatch.setattr("app.services.conversation_chat.chat_stream_with_fallback", _fake_stream)

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        events = await _consume(cc.stream_message(
            db=db_session, user=user, conversation_id=c.id,
            chart=chart, message="我的情绪模式像哪个电影", bypass_divination=False,
            ticket=ticket,
        ))

        # media + secondary=personality 现在通过 retrieval3 composer 派发;
        # 验证 composer 被调用,且接收到正确的 intent + secondary + focus。
        assert retrieve_calls == [{
            "intent": "media",
            "secondary_intents": ["personality"],
            "user_message": "我的情绪模式像哪个电影",
            "retrieval_focus": ["性情", "情绪模式", "五行刚柔"],
        }]
        assert any(e["type"] == "retrieval" for e in events)
        intent_event = events[0]
        assert intent_event["type"] == "intent"
        assert intent_event["needs"]["classics"] is True
        assert intent_event["retrieval_plan"]["enabled"] is True
        assert stream_kwargs["disable_thinking"] is True


async def test_planner_can_disable_classics_for_career_intent(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    route_plan = {
        "intent": "career",
        "reason": "简单追问，不需要重新检索",
        "source": "llm",
        "needs": {
            "chart": True,
            "classics": False,
            "memory": True,
            "hepan": True,
            "divination": False,
        },
        "retrieval_plan": {
            "enabled": False,
            "focus": [],
            "reason": "上一轮已有依据",
        },
        "artifact": {"enabled": False, "kind": None, "reason": ""},
        "answer_plan": {
            "format": "short_answer",
            "style": "直接接上文回答",
            "should_clarify": False,
        },
    }

    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        async def _classify(**_kwargs):
            return route_plan

        async def _retrieve(*_args, **_kwargs):
            raise AssertionError("planner disabled classics; retrieval should not run")

        monkeypatch.setattr("app.services.conversation_chat.classify", _classify)
        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart", _retrieve)
        monkeypatch.setattr("app.services.conversation_chat.compose_retrieval3", _retrieve)
        monkeypatch.setattr(
            "app.services.conversation_chat.chat_stream_with_fallback",
            _fake_stream_factory(["短答"]),
        )

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        events = await _consume(cc.stream_message(
            db=db_session, user=user, conversation_id=c.id,
            chart=chart, message="那怎么落到工作上", bypass_divination=False,
            ticket=ticket,
        ))

        assert not any(e["type"] == "retrieval" for e in events)


async def test_main_chat_injects_selected_hepan_detail_context(
    monkeypatch, db_session, user_and_dek
):
    user, dek = user_and_dek
    stream_kwargs = {}

    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        from app.models.hepan_invite import HepanInvite

        invite = HepanInvite(
            slug="h_ctx000001",
            a_birth_hash="a" * 64,
            a_type_id="01",
            a_state="绽放",
            a_day_stem="甲",
            a_nickname="小夜灯",
            b_birth_hash="b" * 64,
            b_type_id="11",
            b_state="蓄力",
            b_day_stem="己",
            b_nickname="多肉",
            status="completed",
            user_id=user.id,
            a_birth_input=_tiny_paipan(day="甲戌", gender="male", year=2003, city="长沙")["birthInput"],
            a_paipan=_tiny_paipan(day="甲戌", gender="male", year=2003, city="长沙"),
            b_birth_input=_tiny_paipan(day="己未", gender="female", year=2001, city="杭州")["birthInput"],
            b_paipan=_tiny_paipan(day="己未", gender="female", year=2001, city="杭州"),
        )
        db_session.add(invite)
        await db_session.flush()

        route_plan = {
            "intent": "relationship",
            "reason": "用户围绕合盘关系提问",
            "source": "llm",
            "needs": {"chart": True, "classics": False, "memory": True, "hepan": True},
            "retrieval_plan": {"enabled": False, "focus": []},
            "artifact": {"enabled": False, "kind": None, "reason": ""},
            "answer_plan": {"format": "core_then_bullets", "style": "结合双方命盘回答"},
        }

        async def _classify(**_kwargs):
            return route_plan

        async def _fake_stream(**kwargs):
            stream_kwargs.update(kwargs)
            async for ev in _fake_stream_factory(["合盘回答"])(**kwargs):
                yield ev

        async def _no_retr(*_args, **_kwargs):
            return []

        monkeypatch.setattr("app.services.conversation_chat.classify", _classify)
        monkeypatch.setattr("app.services.conversation_chat.chat_stream_with_fallback", _fake_stream)
        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart", _no_retr)
        monkeypatch.setattr("app.services.conversation_chat.compose_retrieval3", _no_retr)

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        await _consume(cc.stream_message(
            db=db_session,
            user=user,
            conversation_id=c.id,
            chart=chart,
            message="我们适合一起做项目吗",
            bypass_divination=False,
            ticket=ticket,
            client_context={
                "view": "chat",
                "hepan": {"slug": "h_ctx000001", "label": "小夜灯 × 多肉"},
            },
        ))

        system_prompt = stream_kwargs["messages"][0]["content"]
        assert "【当前合盘上下文】" in system_prompt
        assert "小夜灯 × 多肉" in system_prompt
        assert "A方命盘" in system_prompt
        assert "B方命盘" in system_prompt
        assert "公历:2003-08-29 08:25" in system_prompt
        assert "出生地:长沙" in system_prompt
        assert "公历:2001-08-29 08:25" in system_prompt
        assert "性别  女命" in system_prompt


async def test_divination_writes_cta_and_redirects(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        monkeypatch.setattr("app.services.conversation_chat.classify",
                             _fake_classify(intent="divination", source="keyword"))

        async def _boom_expert(**_):
            raise AssertionError("expert should not run on divination redirect")
            yield  # noqa
        monkeypatch.setattr("app.services.conversation_chat.chat_stream_with_fallback",
                             _boom_expert)

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        events = await _consume(cc.stream_message(
            db=db_session, user=user, conversation_id=c.id,
            chart=chart, message="我能不能买这个房", bypass_divination=False,
            ticket=ticket,
        ))
        await db_session.flush()

        types = [e["type"] for e in events]
        assert "redirect" in types
        assert types[-1] == "done"

        page = await msg_svc.paginate(db_session, conversation_id=c.id,
                                       before=None, limit=10)
        roles = [m.role for m in page["items"]]
        assert roles == ["cta", "user"]
        assert page["items"][0].meta == {"question": "我能不能买这个房"}


async def test_bypass_divination_consumes_existing_cta(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()
        await msg_svc.insert(db_session, conversation_id=c.id, role="cta",
                              content=None, meta={"question": "old"})
        await db_session.flush()

        monkeypatch.setattr("app.services.conversation_chat.classify",
                             _fake_classify(intent="divination", source="keyword"))
        monkeypatch.setattr("app.services.conversation_chat.chat_stream_with_fallback",
                             _fake_stream_factory(["分", "析"]))
        async def _no_retr(*a, **kw):
            return []
        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart", _no_retr)
        monkeypatch.setattr("app.services.conversation_chat.compose_retrieval3", _no_retr)

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        events = await _consume(cc.stream_message(
            db=db_session, user=user, conversation_id=c.id,
            chart=chart, message="还是直接分析吧", bypass_divination=True,
            ticket=ticket,
        ))
        await db_session.flush()

        page = await msg_svc.paginate(db_session, conversation_id=c.id,
                                       before=None, limit=10)
        roles = [m.role for m in page["items"]]
        assert "cta" not in roles
        assert "assistant" in roles


async def test_llm_error_keeps_user_msg_no_assistant(monkeypatch, db_session, user_and_dek):
    user, dek = user_and_dek
    with user_dek_context(dek):
        chart = await _make_chart(db_session, user)
        c = await conv_svc.create_conversation(db_session, user, chart.id)
        await db_session.flush()

        monkeypatch.setattr("app.services.conversation_chat.classify",
                             _fake_classify(intent="career"))
        monkeypatch.setattr(
            "app.services.conversation_chat.chat_stream_with_fallback",
            _fake_stream_factory_error(UpstreamLLMError(code="UPSTREAM_LLM_TIMEOUT", message="t/o")),
        )
        async def _no_retr(*a, **kw):
            return []
        monkeypatch.setattr("app.services.conversation_chat.retrieve_for_chart", _no_retr)
        monkeypatch.setattr("app.services.conversation_chat.compose_retrieval3", _no_retr)

        ticket = QuotaTicket(user=user, kind="chat_message", limit=30, _db=db_session)
        events = await _consume(cc.stream_message(
            db=db_session, user=user, conversation_id=c.id,
            chart=chart, message="问问事业", bypass_divination=False,
            ticket=ticket,
        ))
        await db_session.flush()

        types = [e["type"] for e in events]
        assert types[-1] == "error"

        page = await msg_svc.paginate(db_session, conversation_id=c.id,
                                       before=None, limit=10)
        roles = [m.role for m in page["items"]]
        assert roles == ["user"]
        # Ticket must NOT have been committed when the LLM errored
        assert not ticket._committed
