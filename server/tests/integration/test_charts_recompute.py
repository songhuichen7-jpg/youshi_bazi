"""POST /api/charts/:id/recompute integration tests."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.conftest import register_user


async def _register(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    return await register_user(client, phone)


async def _make(client, cookie, label="L"):
    body = {"birth_input":{"year":1990,"month":5,"day":12,"hour":12,"gender":"male"},
            "label": label}
    r = await client.post("/api/charts", cookies={"session": cookie}, json=body)
    assert r.status_code == 201
    return r.json()["chart"]["id"]


@pytest.mark.asyncio
async def test_recompute_happy(client, database_url):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie)
    # Tamper engine_version to pretend old
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await s.execute(text("UPDATE charts SET engine_version='0.0.0' WHERE id=:cid"),
                        {"cid": cid})
        await s.commit()
    await engine.dispose()

    r = await client.post(f"/api/charts/{cid}/recompute", cookies={"session": cookie})
    assert r.status_code == 200
    body = r.json()
    assert body["cache_stale"] is False
    assert body["cache_slots"] == []
    import paipan
    assert body["chart"]["engine_version"] == paipan.VERSION


@pytest.mark.asyncio
async def test_recompute_clears_cache(client, database_url):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie)
    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await s.execute(text("""
            INSERT INTO chart_cache (chart_id, kind, key, content, model_used,
                                      tokens_used, generated_at, regen_count)
            VALUES (:cid, 'verdicts', '', NULL, 'mimo-v2-pro', 10, now(), 0)
        """), {"cid": cid})
        await s.commit()
    await engine.dispose()

    r = await client.post(f"/api/charts/{cid}/recompute", cookies={"session": cookie})
    assert r.status_code == 200

    engine = create_async_engine(str(database_url))
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        n = (await s.execute(text("SELECT count(*) FROM chart_cache WHERE chart_id=:cid"),
                              {"cid": cid})).scalar()
    await engine.dispose()
    assert n == 0


@pytest.mark.asyncio
async def test_recompute_cross_user_404(client):
    cookie_a, _ = await _register(client)
    cookie_b, _ = await _register(client)
    cid = await _make(client, cookie_a)
    r = await client.post(f"/api/charts/{cid}/recompute", cookies={"session": cookie_b})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_recompute_soft_deleted_404(client):
    cookie, _ = await _register(client)
    cid = await _make(client, cookie)
    await client.delete(f"/api/charts/{cid}", cookies={"session": cookie})
    r = await client.post(f"/api/charts/{cid}/recompute", cookies={"session": cookie})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_recompute_nonexistent_404(client):
    cookie, _ = await _register(client)
    r = await client.post(f"/api/charts/{uuid.uuid4()}/recompute", cookies={"session": cookie})
    assert r.status_code == 404
