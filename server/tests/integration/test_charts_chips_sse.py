"""SSE: POST /api/charts/:id/chips — FAST_MODEL, no cache, no quota."""
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
async def test_chips_happy(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-flash":['["事业?","婚姻?","财运?"]']})
    events = await consume_sse(client, f"/api/charts/{cid}/chips",
                                cookies={"session": cookie}, json_body={})
    model_evts = [e for e in events if e["type"] == "model"]
    from app.core.config import settings
    assert any(m["modelUsed"] == settings.llm_fast_model for m in model_evts)
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_chips_does_not_write_cache(client, database_url, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-flash":["[]"]})
    await consume_sse(client, f"/api/charts/{cid}/chips",
                       cookies={"session": cookie}, json_body={})
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        n = (await s.execute(text("SELECT count(*) FROM chart_cache WHERE chart_id=:cid"),
                              {"cid": cid})).scalar()
    await engine.dispose()
    assert n == 0


@pytest.mark.asyncio
async def test_chips_cross_user_404(client):
    cookie_a, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cookie_b, _ = await register_user(client, f"+86139{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie_a)
    r = await client.post(f"/api/charts/{cid}/chips", cookies={"session": cookie_b})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_chips_llm_error_emits_error_event(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-flash":[]}, raise_on_model={"mimo-v2-flash"})
    events = await consume_sse(client, f"/api/charts/{cid}/chips",
                                cookies={"session": cookie}, json_body={})
    assert any(e["type"] == "error" for e in events)
