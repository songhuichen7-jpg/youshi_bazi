"""SSE: POST /api/charts/:id/sections."""
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
async def test_sections_career_happy(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-pro":["事业段落"]})
    events = await consume_sse(client, f"/api/charts/{cid}/sections",
                                cookies={"session": cookie},
                                json_body={"section": "career"})
    assert events[-1]["full"] == "事业段落"


@pytest.mark.asyncio
async def test_sections_invalid_section_422(client):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    r = await client.post(f"/api/charts/{cid}/sections",
                           cookies={"session": cookie},
                           json={"section": "invalid"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sections_independent_cache_per_section(client, database_url, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-pro":["x"]})
    for sec in ("career","wealth"):
        await consume_sse(client, f"/api/charts/{cid}/sections",
                           cookies={"session": cookie},
                           json_body={"section": sec})
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        keys = [row.key for row in (await s.execute(
            text("SELECT key FROM chart_cache WHERE chart_id=:cid AND kind='section'"),
            {"cid": cid},
        )).all()]
    await engine.dispose()
    assert set(keys) == {"career", "wealth"}


@pytest.mark.asyncio
async def test_sections_force_regen_429_when_exhausted(client, database_url):
    cookie, user = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    from app.core.quotas import QUOTAS, today_beijing
    limit = QUOTAS[user["plan"]]["section_regen"]
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await s.execute(text("""
            INSERT INTO chart_cache (chart_id, kind, key, content, model_used,
                                      tokens_used, generated_at, regen_count)
            VALUES (:cid, 'section', 'career', NULL, 'mimo-v2-pro', 10, now(), 0)
        """), {"cid": cid})
        await s.execute(text("""
            INSERT INTO quota_usage (user_id, period, kind, count, updated_at)
            VALUES (:uid, :p, 'section_regen', :lim, now())
        """), {"uid": user["id"], "p": today_beijing(), "lim": limit})
        await s.commit()
    await engine.dispose()
    r = await client.post(f"/api/charts/{cid}/sections?force=true",
                           cookies={"session": cookie},
                           json={"section":"career"})
    assert r.status_code == 429


@pytest.mark.asyncio
async def test_sections_llm_error_sse_error(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-pro":[],"mimo-v2-flash":[]},
                      raise_on_model={"mimo-v2-pro","mimo-v2-flash"})
    events = await consume_sse(client, f"/api/charts/{cid}/sections",
                                cookies={"session": cookie},
                                json_body={"section":"career"})
    assert any(e["type"] == "error" for e in events)
