"""GET /api/charts + GET /api/charts/:id integration tests."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.conftest import register_user


async def _register(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    return await register_user(client, phone)


async def _make(client, cookie, label=None):
    body = {
        "birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"},
    }
    if label is not None:
        body["label"] = label
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    assert r.status_code == 201, r.text
    return r.json()["chart"]["id"]


@pytest.mark.asyncio
async def test_list_empty(client):
    cookie, _ = await _register(client)
    r = await client.get("/api/charts", cookies={"session": cookie})
    assert r.status_code == 200
    assert r.json() == {"items": []}


@pytest.mark.asyncio
async def test_list_desc_order(client):
    # 升级到 pro 档位 — lite 默认 cap=2，造第 3 张 chart 就 409。
    from .conftest import upgrade_user_plan
    cookie, user = await _register(client)
    await upgrade_user_plan(user["id"], "pro")
    a = await _make(client, cookie, "A")
    b = await _make(client, cookie, "B")
    c = await _make(client, cookie, "C")
    r = await client.get("/api/charts", cookies={"session": cookie})
    ids = [it["id"] for it in r.json()["items"]]
    assert ids == [c, b, a]


@pytest.mark.asyncio
async def test_list_unauthenticated_401(client):
    r = await client.get("/api/charts")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_detail_happy(client):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie, "X")
    r = await client.get(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 200
    body = r.json()
    assert body["chart"]["id"] == cid
    assert body["chart"]["label"] == "X"
    assert body["cache_slots"] == []
    assert body["cache_stale"] is False
    assert body["warnings"] == []


@pytest.mark.asyncio
async def test_get_detail_nonexistent_404(client):
    cookie, _ = await _register(client)
    r = await client.get(f"/api/charts/{uuid.uuid4()}", cookies={"session": cookie})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "CHART_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_detail_cache_stale_flag(client, database_url):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie)

    # Simulate an engine upgrade by bumping the stored engine_version.
    engine = create_async_engine(str(database_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(
            text("UPDATE charts SET engine_version = '0.0.0' WHERE id = :cid"),
            {"cid": cid},
        )
        await s.commit()
    await engine.dispose()

    r = await client.get(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 200
    assert r.json()["cache_stale"] is True
    # GET must NOT have written anything — engine_version stays '0.0.0'.
    engine = create_async_engine(str(database_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        ver = (await s.execute(
            text("SELECT engine_version FROM charts WHERE id = :cid"), {"cid": cid},
        )).scalar_one()
    await engine.dispose()
    assert ver == "0.0.0"


@pytest.mark.asyncio
async def test_get_detail_soft_deleted_404(client, database_url):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie)
    # Soft-delete via DELETE endpoint.
    r = await client.delete(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 204
    r = await client.get(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_excludes_soft_deleted(client):
    cookie, _ = await _register(client)
    keep = await _make(client, cookie, "keep")
    gone = await _make(client, cookie, "gone")
    r = await client.delete(f"/api/charts/{gone}", cookies={"session": cookie})
    assert r.status_code == 204
    r = await client.get("/api/charts", cookies={"session": cookie})
    ids = [it["id"] for it in r.json()["items"]]
    assert ids == [keep]
