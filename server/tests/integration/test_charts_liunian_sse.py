"""SSE: POST /api/charts/:id/liunian."""
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
async def test_liunian_happy(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-pro":["流年内容"]})
    events = await consume_sse(client, f"/api/charts/{cid}/liunian",
                                cookies={"session": cookie},
                                json_body={"dayun_index": 1, "year_index": 3})
    assert events[-1]["full"] == "流年内容"


@pytest.mark.asyncio
async def test_liunian_missing_body_422(client):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    r = await client.post(f"/api/charts/{cid}/liunian", cookies={"session": cookie},
                           json={"dayun_index": 0})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_liunian_cache_key_compound(client, database_url, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-pro":["x"]})
    await consume_sse(client, f"/api/charts/{cid}/liunian",
                       cookies={"session": cookie},
                       json_body={"dayun_index":2, "year_index":5})
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        key = (await s.execute(
            text("SELECT key FROM chart_cache WHERE chart_id=:cid AND kind='liunian'"),
            {"cid": cid},
        )).scalar()
    await engine.dispose()
    assert key == "2:5"
