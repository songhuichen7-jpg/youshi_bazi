"""chart_llm.stream_chart_llm: end-to-end generator with mocked LLM client."""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def db_session(database_url):
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            maker = async_sessionmaker(bind=conn, expire_on_commit=False)
            async with maker() as s:
                yield s
            await trans.rollback()
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def seeded(db_session):
    from app.db_types import user_dek_context
    from app.models.chart import Chart
    from app.models.user import User
    dek = os.urandom(32)
    u = User(phone=f"+86138{uuid.uuid4().int % 10**8:08d}",
             dek_ciphertext=b"\x00" * 44)
    db_session.add(u); await db_session.flush()
    with user_dek_context(dek):
        c = Chart(
            user_id=u.id,
            birth_input={"year":1990,"month":5,"day":12,"hour":12,"gender":"male"},
            paipan={"sizhu":{"year":"庚午"}, "hourUnknown":False},
            engine_version="0.1.0",
        )
        db_session.add(c); await db_session.flush()
    return u, c, dek


def _fake_stream_fn(chunks: list[str], tokens: int = 30):
    """Replacement for chat_stream_with_fallback — yields prescribed events."""
    async def _stream(**kwargs):
        yield {"type": "model", "modelUsed": "mimo-v2-pro"}
        for c in chunks:
            yield {"type": "delta", "text": c}
        yield {"type": "done", "full": "".join(chunks), "tokens_used": tokens,
               "prompt_tokens": 10, "completion_tokens": tokens - 10}
    return _stream


def _fake_build_messages(chart, retrieved, **kw):
    return [{"role":"system","content":"test"}, {"role":"user","content":"do it"}]


async def _fake_retrieve(chart, kind):
    return []


@pytest.mark.asyncio
async def test_stream_chart_llm_cache_miss_generates_and_writes(db_session, seeded, monkeypatch):
    from app.db_types import user_dek_context
    from app.services import chart_llm
    monkeypatch.setattr(chart_llm, "chat_stream_with_fallback",
                        _fake_stream_fn(["hello ", "world"], tokens=42))
    monkeypatch.setattr(chart_llm, "retrieve_for_chart", _fake_retrieve)

    user, chart, dek = seeded
    with user_dek_context(dek):
        events = []
        async for raw in chart_llm.stream_chart_llm(
            db_session, user, chart,
            kind="verdicts", key="", force=False, cache_row=None, ticket=None,
            build_messages=_fake_build_messages,
            retrieval_kind="meta",
            temperature=0.7, max_tokens=3000, tier="primary",
        ):
            events.append(raw)
        await db_session.flush()
        row = await chart_llm.get_cache_row(db_session, chart.id, "verdicts", "")
    assert row is not None
    assert row.content == "hello world"
    assert row.regen_count == 0


@pytest.mark.asyncio
async def test_stream_chart_llm_cache_hit_replays_without_llm(db_session, seeded, monkeypatch):
    from app.db_types import user_dek_context
    from app.services import chart_llm

    user, chart, dek = seeded
    with user_dek_context(dek):
        await chart_llm.upsert_cache(db_session,
            chart_id=chart.id, kind="verdicts", key="",
            content="cached content", model_used="mimo-v2-pro",
            tokens_used=50, regen_increment=False)
        await db_session.flush()
        cache_row = await chart_llm.get_cache_row(db_session, chart.id, "verdicts", "")

    def _boom(**kw): raise AssertionError("LLM should not be called on cache hit")
    monkeypatch.setattr(chart_llm, "chat_stream_with_fallback", _boom)

    with user_dek_context(dek):
        events = []
        async for raw in chart_llm.stream_chart_llm(
            db_session, user, chart,
            kind="verdicts", key="", force=False,
            cache_row=cache_row, ticket=None,
            build_messages=_fake_build_messages,
            retrieval_kind="meta",
            temperature=0.7, max_tokens=3000, tier="primary",
        ):
            events.append(raw)
    assert any(b'"source":"cache"' in e for e in events)


@pytest.mark.asyncio
async def test_stream_chart_llm_upstream_error_no_cache_write(db_session, seeded, monkeypatch):
    from app.db_types import user_dek_context
    from app.services import chart_llm
    from app.services.exceptions import UpstreamLLMError

    async def _erroring(**kw):
        yield {"type": "model", "modelUsed": "mimo-v2-pro"}
        raise UpstreamLLMError(code="UPSTREAM_LLM_FAILED", message="boom")

    monkeypatch.setattr(chart_llm, "chat_stream_with_fallback", _erroring)
    monkeypatch.setattr(chart_llm, "retrieve_for_chart", _fake_retrieve)

    user, chart, dek = seeded
    with user_dek_context(dek):
        events = []
        async for raw in chart_llm.stream_chart_llm(
            db_session, user, chart,
            kind="verdicts", key="", force=False, cache_row=None, ticket=None,
            build_messages=_fake_build_messages, retrieval_kind="meta",
            temperature=0.7, max_tokens=3000, tier="primary",
        ):
            events.append(raw)
        await db_session.flush()
        row = await chart_llm.get_cache_row(db_session, chart.id, "verdicts", "")
    assert row is None
    assert any(b'"type":"error"' in e for e in events)


@pytest.mark.asyncio
async def test_stream_chart_llm_passes_first_delta_timeout_from_settings(
    db_session, seeded, monkeypatch,
):
    """Task 1 (cleanup): settings.llm_stream_first_delta_ms must flow through."""
    from app.db_types import user_dek_context
    from app.services import chart_llm

    # Capture kwargs passed to chat_stream_with_fallback
    captured = {}

    async def _capturing_stream(**kwargs):
        captured.update(kwargs)
        yield {"type": "model", "modelUsed": "mimo-v2-pro"}
        yield {"type": "delta", "text": "x"}
        yield {"type": "done", "full": "x", "tokens_used": 1,
               "prompt_tokens": 1, "completion_tokens": 0}

    monkeypatch.setattr(chart_llm, "chat_stream_with_fallback", _capturing_stream)

    async def _empty_retrieve(chart, kind):
        return []
    monkeypatch.setattr(chart_llm, "retrieve_for_chart", _empty_retrieve)

    monkeypatch.setattr("app.services.chart_llm.settings.llm_stream_first_delta_ms", 7500)

    def _build(chart_paipan, retrieved):
        return [{"role":"system","content":"s"}, {"role":"user","content":"u"}]

    user, chart, dek = seeded
    with user_dek_context(dek):
        async for _ in chart_llm.stream_chart_llm(
            db_session, user, chart,
            kind="verdicts", key="", force=False, cache_row=None, ticket=None,
            build_messages=_build, retrieval_kind="meta",
            temperature=0.7, max_tokens=3000, tier="primary",
        ):
            pass

    assert captured.get("first_delta_timeout_ms") == 7500


@pytest.mark.asyncio
async def test_stream_chart_llm_commits_ticket_before_yielding_done(
    db_session, seeded, monkeypatch,
):
    """Task 4 (cleanup): on success, ticket.commit happens before `done` event.

    If commit races (QuotaExceededError), user sees `error` INSTEAD OF `done`
    — never both.
    """
    from app.db_types import user_dek_context
    from app.services import chart_llm

    class _RacingTicket:
        kind = "verdicts_regen"
        async def commit(self):
            raise RuntimeError("simulated race: quota exceeded mid-request")

    async def _stream(**kw):
        yield {"type": "model", "modelUsed": "mimo-v2-pro"}
        yield {"type": "delta", "text": "content"}
        yield {"type": "done", "full": "content", "tokens_used": 10,
               "prompt_tokens": 5, "completion_tokens": 5}
    monkeypatch.setattr(chart_llm, "chat_stream_with_fallback", _stream)

    async def _retrieve(chart, kind):
        return []
    monkeypatch.setattr(chart_llm, "retrieve_for_chart", _retrieve)

    user, chart, dek = seeded
    events = []
    with user_dek_context(dek):
        async for raw in chart_llm.stream_chart_llm(
            db_session, user, chart,
            kind="verdicts", key="", force=True,
            cache_row=None, ticket=_RacingTicket(),
            build_messages=lambda p, r: [{"role":"s","content":"x"}],
            retrieval_kind="meta",
            temperature=0.7, max_tokens=3000, tier="primary",
        ):
            events.append(raw)

    types_on_wire = []
    for raw in events:
        if b'"type":"done"' in raw:
            types_on_wire.append("done")
        elif b'"type":"error"' in raw:
            types_on_wire.append("error")
        elif b'"type":"delta"' in raw:
            types_on_wire.append("delta")
        elif b'"type":"model"' in raw:
            types_on_wire.append("model")

    # Race path: no done event should have been emitted
    assert "done" not in types_on_wire, f"expected no done event on race; got: {types_on_wire}"
    assert "error" in types_on_wire


@pytest.mark.asyncio
async def test_stream_chart_llm_race_does_not_write_cache(
    db_session, seeded, monkeypatch,
):
    """Task 4 (cleanup): ticket race → cache is NOT written.

    Before Task 4: cache WAS written before commit, causing a "free regen".
    After Task 4: commit is gated before cache write; race blocks cache.
    """
    from app.db_types import user_dek_context
    from app.services import chart_llm

    class _RacingTicket:
        kind = "verdicts_regen"
        async def commit(self):
            raise RuntimeError("race")

    async def _stream(**kw):
        yield {"type": "model", "modelUsed": "mimo-v2-pro"}
        yield {"type": "delta", "text": "new content"}
        yield {"type": "done", "full": "new content", "tokens_used": 12,
               "prompt_tokens": 6, "completion_tokens": 6}
    monkeypatch.setattr(chart_llm, "chat_stream_with_fallback", _stream)

    async def _retrieve(chart, kind):
        return []
    monkeypatch.setattr(chart_llm, "retrieve_for_chart", _retrieve)

    user, chart, dek = seeded
    with user_dek_context(dek):
        async for _ in chart_llm.stream_chart_llm(
            db_session, user, chart,
            kind="verdicts", key="", force=True,
            cache_row=None, ticket=_RacingTicket(),
            build_messages=lambda p, r: [{"role":"s","content":"x"}],
            retrieval_kind="meta",
            temperature=0.7, max_tokens=3000, tier="primary",
        ):
            pass

    # Cache must NOT have been written on race
    row = await chart_llm.get_cache_row(db_session, chart.id, "verdicts", "")
    assert row is None
