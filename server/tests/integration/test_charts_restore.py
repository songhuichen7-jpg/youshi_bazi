"""POST /api/charts/:id/restore integration tests."""
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
    return r.json()["chart"]["id"]


@pytest.mark.asyncio
async def test_restore_happy(client):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie, "coming back")
    await client.delete(f"/api/charts/{cid}", cookies={"session": cookie})
    r = await client.post(f"/api/charts/{cid}/restore", cookies={"session": cookie})
    assert r.status_code == 200
    assert r.json()["chart"]["label"] == "coming back"
    r = await client.get(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_restore_not_soft_deleted_404(client):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie)
    r = await client.post(f"/api/charts/{cid}/restore", cookies={"session": cookie})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_restore_nonexistent_404(client):
    cookie, _ = await _register(client)
    r = await client.post(
        f"/api/charts/{uuid.uuid4()}/restore", cookies={"session": cookie},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_restore_cross_user_404(client):
    cookie_a, _ = await _register(client)
    cookie_b, _ = await _register(client)
    cid = await _make(client, cookie_a)
    await client.delete(f"/api/charts/{cid}", cookies={"session": cookie_a})
    r = await client.post(f"/api/charts/{cid}/restore", cookies={"session": cookie_b})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_restore_past_window_404(client, database_url):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie)
    await client.delete(f"/api/charts/{cid}", cookies={"session": cookie})

    engine = create_async_engine(str(database_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(
            text("UPDATE charts SET deleted_at = now() - INTERVAL '31 days' WHERE id = :cid"),
            {"cid": cid},
        )
        await s.commit()
    await engine.dispose()

    r = await client.post(f"/api/charts/{cid}/restore", cookies={"session": cookie})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_restore_at_cap_409(client):
    # 升级 pro 档位（cap=20）— 把 cap 填满后 restore 软删 chart 会触发 409。
    # 默认 lite 档位 cap=2，没法干净地走"达 cap 后 restore"路径。
    from .conftest import upgrade_user_plan
    cookie, user = await _register(client)
    await upgrade_user_plan(user["id"], "pro")
    victim = await _make(client, cookie, "victim")
    await client.delete(f"/api/charts/{victim}", cookies={"session": cookie})
    for _ in range(20):
        await _make(client, cookie)
    r = await client.post(f"/api/charts/{victim}/restore", cookies={"session": cookie})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "CHART_LIMIT_EXCEEDED"
