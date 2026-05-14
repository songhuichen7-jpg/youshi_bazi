from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.card_share import CardShare


@pytest.mark.asyncio
async def test_post_card_returns_full_payload(client):
    resp = await client.post("/api/card", json={
        "birth": {"year": 1998, "month": 7, "day": 15, "hour": 14, "minute": 0},
        "nickname": "小满",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["type_id"] in [f"{i:02d}" for i in range(1, 21)]
    assert data["nickname"] == "小满"
    assert data["precision"] == "4-pillar"
    assert data["share_slug"].startswith("c_")
    assert len(data["subtags"]) == 3


@pytest.mark.asyncio
async def test_post_card_no_auth_required(client):
    resp = await client.post("/api/card", json={
        "birth": {"year": 2000, "month": 1, "day": 1, "hour": -1, "minute": 0},
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["precision"] == "3-pillar"


@pytest.mark.asyncio
async def test_post_card_422_on_invalid_year(client):
    resp = await client.post("/api/card", json={
        "birth": {"year": 1800, "month": 1, "day": 1, "hour": 0, "minute": 0},
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_card_persists_share_row(client):
    resp = await client.post("/api/card", json={
        "birth": {"year": 1998, "month": 7, "day": 15, "hour": 14, "minute": 0},
    })
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    slug = payload["share_slug"]

    # Verify a card_shares row was written using a fresh session
    from app.core.db import _ensure_engine
    session_maker = _ensure_engine()
    async with session_maker() as db:
        row = (await db.execute(
            select(CardShare).where(CardShare.slug == slug)
        )).scalar_one()
        assert row.type_id == payload["type_id"]
        assert row.cosmic_name == payload["cosmic_name"]


@pytest.mark.asyncio
async def test_get_card_by_slug_returns_preview_only(client):
    # Create a card first
    create_resp = await client.post("/api/card", json={
        "birth": {"year": 1998, "month": 7, "day": 15, "hour": 14, "minute": 0},
        "nickname": "小满",
    })
    slug = create_resp.json()["share_slug"]

    # Fetch preview
    preview = await client.get(f"/api/card/{slug}")
    assert preview.status_code == 200, preview.text
    data = preview.json()
    # Preview fields only
    assert data["cosmic_name"]
    assert data["suffix"]
    assert data["illustration_url"]
    assert data["slug"] == slug
    # Sensitive fields MUST NOT be present
    assert "subtags" not in data
    assert "golden_line" not in data
    assert "one_liner" not in data
    assert "type_id" not in data  # not even type_id — just the headline name


@pytest.mark.asyncio
async def test_get_card_by_slug_404_on_unknown(client):
    resp = await client.get("/api/card/c_doesnotexist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_card_by_slug_bumps_share_count(client):
    create_resp = await client.post("/api/card", json={
        "birth": {"year": 1998, "month": 7, "day": 15, "hour": 14, "minute": 0},
    })
    slug = create_resp.json()["share_slug"]

    # Hit preview 3 times
    for _ in range(3):
        r = await client.get(f"/api/card/{slug}")
        assert r.status_code == 200

    # Read the DB row and check share_count
    from app.core.db import _ensure_engine
    from app.models.card_share import CardShare
    session_maker = _ensure_engine()
    async with session_maker() as db:
        row = (await db.execute(
            select(CardShare).where(CardShare.slug == slug)
        )).scalar_one()
        assert row.share_count == 3
