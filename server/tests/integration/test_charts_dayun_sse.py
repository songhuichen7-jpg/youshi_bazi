"""SSE: POST /api/charts/:id/dayun/{index}."""
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
async def test_dayun_step_2_happy(client, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-pro":["大运第3步..."]})
    events = await consume_sse(client, f"/api/charts/{cid}/dayun/2",
                                cookies={"session": cookie}, json_body={})
    assert events[-1]["full"] == "大运第3步..."


@pytest.mark.asyncio
async def test_dayun_out_of_range_422(client):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    r = await client.post(f"/api/charts/{cid}/dayun/99", cookies={"session": cookie})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_dayun_cache_key_is_index(client, database_url, monkeypatch):
    cookie, _ = await register_user(client, f"+86138{uuid.uuid4().int % 10**8:08d}")
    cid = await _make(client, cookie)
    patch_llm_client(monkeypatch, {"mimo-v2-pro":["x"]})
    await consume_sse(client, f"/api/charts/{cid}/dayun/3",
                       cookies={"session": cookie}, json_body={})
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        key = (await s.execute(
            text("SELECT key FROM chart_cache WHERE chart_id=:cid AND kind='dayun_step'"),
            {"cid": cid},
        )).scalar()
    await engine.dispose()
    assert key == "3"
