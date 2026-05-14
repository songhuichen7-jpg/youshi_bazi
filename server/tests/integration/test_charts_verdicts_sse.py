"""SSE: POST /api/charts/:id/verdicts."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.conftest import register_user
from tests.integration.test_sse_helpers import consume_sse, patch_llm_client


async def _make(client, cookie):
    body = {"birth_input":{"year":1990,"month":5,"day":12,"hour":12,"gender":"male"}}
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    return r.json()["chart"]["id"]


@pytest.mark.asyncio
async def test_verdicts_cache_miss_generates_and_writes(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-pro": ["整体判词：", "庚金带杀..."]})

    events = await consume_sse(client, f"/api/charts/{cid}/verdicts",
                                cookies={"session": cookie}, json_body={})
    types = [e["type"] for e in events]
    assert "model" in types and "delta" in types and "done" in types
    full = events[-1]["full"]
    assert "庚金" in full


@pytest.mark.asyncio
async def test_verdicts_cache_hit_replays(client, database_url, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)

    # Seed cache via direct INSERT — chart_cache.content is EncryptedText (bytea);
    # use the ORM to get proper encryption via the DEK set by current_user.
    # Simpler: test doesn't need real content; use pg_insert with an empty string.
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await s.execute(text("""
            INSERT INTO chart_cache (chart_id, kind, key, content, model_used,
                                      tokens_used, generated_at, regen_count)
            VALUES (:cid, 'verdicts', '', NULL, 'mimo-v2-pro', 100, now(), 0)
        """), {"cid": cid})
        await s.commit()
    await engine.dispose()

    # LLM must NOT be called — install a boom
    def _boom(**kw): raise AssertionError("no LLM on cache hit")
    from app.llm import client as c
    monkeypatch.setattr(c._client.chat.completions, "create", _boom)

    events = await consume_sse(client, f"/api/charts/{cid}/verdicts",
                                cookies={"session": cookie}, json_body={})
    sources = [e.get("source") for e in events]
    assert "cache" in sources
    # content was NULL-seeded; cache branch still emits model + done (and maybe no deltas)


@pytest.mark.asyncio
async def test_verdicts_force_no_cache_generates_without_quota(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-pro": ["first-gen"]})

    events = await consume_sse(client, f"/api/charts/{cid}/verdicts?force=true",
                                cookies={"session": cookie}, json_body={})
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_verdicts_force_cache_charges_regen_quota(client, database_url, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)

    # Seed cache (NULL content)
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await s.execute(text("""
            INSERT INTO chart_cache (chart_id, kind, key, content, model_used,
                                      tokens_used, generated_at, regen_count)
            VALUES (:cid, 'verdicts', '', NULL, 'mimo-v2-pro', 50, now(), 0)
        """), {"cid": cid})
        await s.commit()
    await engine.dispose()

    patch_llm_client(monkeypatch, {"mimo-v2-pro": ["new content"]})

    events = await consume_sse(client, f"/api/charts/{cid}/verdicts?force=true",
                                cookies={"session": cookie}, json_body={})
    assert events[-1]["type"] == "done"
    assert events[-1]["full"] == "new content"

    r = await client.get("/api/quota", cookies={"session": cookie})
    assert r.json()["usage"]["verdicts_regen"]["used"] == 1


@pytest.mark.asyncio
async def test_verdicts_force_regen_quota_exceeded_429(client, database_url):
    cookie, user = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)

    from app.core.quotas import QUOTAS, today_beijing
    limit = QUOTAS[user["plan"]]["verdicts_regen"]
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await s.execute(text("""
            INSERT INTO chart_cache (chart_id, kind, key, content, model_used,
                                      tokens_used, generated_at, regen_count)
            VALUES (:cid, 'verdicts', '', NULL, 'mimo-v2-pro', 50, now(), 0)
        """), {"cid": cid})
        await s.execute(text("""
            INSERT INTO quota_usage (user_id, period, kind, count, updated_at)
            VALUES (:uid, :p, 'verdicts_regen', :lim, now())
        """), {"uid": user["id"], "p": today_beijing(), "lim": limit})
        await s.commit()
    await engine.dispose()

    r = await client.post(f"/api/charts/{cid}/verdicts?force=true",
                           cookies={"session": cookie})
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "QUOTA_EXCEEDED"


@pytest.mark.asyncio
async def test_verdicts_llm_error_sse_error_no_cache(client, database_url, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-pro":[], "mimo-v2-flash":[]},
                      raise_on_model={"mimo-v2-pro","mimo-v2-flash"})

    events = await consume_sse(client, f"/api/charts/{cid}/verdicts",
                                cookies={"session": cookie}, json_body={})
    assert any(e["type"] == "error" for e in events)

    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        n = (await s.execute(text("SELECT count(*) FROM chart_cache WHERE chart_id=:cid"),
                              {"cid": cid})).scalar()
    await engine.dispose()
    assert n == 0


@pytest.mark.asyncio
async def test_verdicts_fallback_takes_over_on_primary_error(client, monkeypatch):
    """Primary errors at create() → fallback fires and completes the stream."""
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    from app.llm import client as llm_client
    monkeypatch.setattr(llm_client.settings, "llm_model", "deepseek-v4-pro")
    monkeypatch.setattr(llm_client.settings, "llm_fallback_model", "deepseek-v4-flash")
    patch_llm_client(monkeypatch,
                      {"mimo-v2-pro":[], "mimo-v2-flash":["fallback content"]},
                      raise_on_model={"mimo-v2-pro"})

    events = await consume_sse(client, f"/api/charts/{cid}/verdicts",
                                cookies={"session": cookie}, json_body={})
    models = [e["modelUsed"] for e in events if e["type"] == "model"]
    assert "deepseek-v4-flash" in models
    assert events[-1]["full"] == "fallback content"


@pytest.mark.asyncio
async def test_verdicts_cross_user_404(client, monkeypatch):
    cookie_a, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cookie_b, _ = await register_user(client, f"+86139{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie_a)
    r = await client.post(f"/api/charts/{cid}/verdicts", cookies={"session": cookie_b})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_verdicts_unauthenticated_401(client):
    r = await client.post(f"/api/charts/{uuid.uuid4()}/verdicts")
    assert r.status_code == 401
