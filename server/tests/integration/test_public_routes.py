"""Public endpoints: /api/config + /api/cities."""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_config_shape(client):
    r = await client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"require_invite", "engine_version", "max_charts_per_user", "guest_login_enabled"}
    assert isinstance(body["require_invite"], bool)
    assert body["guest_login_enabled"] is True
    # NOTE: max_charts_per_user 之前是全局 15；Plan 5 之后改成 plan-tiered，
    # /api/config 在没有 user 上下文时（公共路由，未鉴权）返回 lite 默认 2。
    # 同 server/app/core/quotas.py:MAX_CHARTS_PER_USER。
    assert body["max_charts_per_user"] == 2
    import paipan
    assert body["engine_version"] == paipan.VERSION


@pytest.mark.asyncio
async def test_cities_returns_list(client):
    r = await client.get("/api/cities")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert len(body["items"]) > 1000
    # each item has shape
    for it in body["items"][:5]:
        assert set(it.keys()) == {"name", "lng", "lat"}


@pytest.mark.asyncio
async def test_cities_sorted_by_name(client):
    r = await client.get("/api/cities")
    names = [it["name"] for it in r.json()["items"]]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_cities_etag_header_present(client):
    r = await client.get("/api/cities")
    assert "etag" in {k.lower() for k in r.headers}
    assert r.headers.get("cache-control") == "public, max-age=86400"


@pytest.mark.asyncio
async def test_cities_if_none_match_returns_304(client):
    r1 = await client.get("/api/cities")
    etag = r1.headers["etag"]
    r2 = await client.get("/api/cities", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.content == b""


@pytest.mark.asyncio
async def test_cities_response_size_under_500kb(client):
    r = await client.get("/api/cities")
    # Raw (uncompressed) body size sanity cap; actual over-the-wire will be
    # much smaller under gzip.
    assert len(r.content) < 500_000


@pytest.mark.asyncio
async def test_config_no_auth_required(client):
    # No cookie → 200 (public route).
    r = await client.get("/api/config")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_cities_no_auth_required(client):
    r = await client.get("/api/cities")
    assert r.status_code == 200
