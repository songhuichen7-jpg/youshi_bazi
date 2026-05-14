from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.event import Event


@pytest.mark.asyncio
async def test_post_track_persists_event(client):
    resp = await client.post("/api/track", json={
        "event": "card_view",
        "properties": {
            "type_id": "04",
            "from": "share_friend",
            "share_slug": "c_abcdefghij",
            "anonymous_id": "a_xyz123",
            "session_id": "s_def456",
            "user_agent": "Mozilla/5.0 ...",
            "viewport": "375x812",
        },
    })
    assert resp.status_code == 204

    from app.core.db import _ensure_engine
    session_maker = _ensure_engine()
    async with session_maker() as db:
        rows = (await db.execute(
            select(Event).where(Event.event == "card_view")
        )).scalars().all()
        assert len(rows) >= 1
        row = rows[-1]
        assert row.type_id == "04"
        assert row.from_param == "share_friend"
        assert row.share_slug == "c_abcdefghij"
        assert row.anonymous_id == "a_xyz123"


@pytest.mark.asyncio
async def test_post_track_rejects_unknown_event(client):
    resp = await client.post("/api/track", json={
        "event": "definitely_not_valid",
        "properties": {},
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_track_accepts_beta_product_events(client):
    resp = await client.post("/api/track", json={
        "event": "hepan_complete",
        "properties": {
            "anonymous_id": "a_beta_hepan",
            "session_id": "s_beta_hepan",
            "hepan_slug": "h_abc123",
            "category": "mirror",
            "state_pair": "绽放x蓄力",
            "route": "/hepan/h_abc123",
        },
    })
    assert resp.status_code == 204

    from app.core.db import _ensure_engine
    session_maker = _ensure_engine()
    async with session_maker() as db:
        row = (await db.execute(
            select(Event)
            .where(Event.event == "hepan_complete")
            .order_by(Event.id.desc())
        )).scalars().first()
        assert row is not None
        assert row.anonymous_id == "a_beta_hepan"
        assert row.extra["hepan_slug"] == "h_abc123"
        assert row.extra["category"] == "mirror"


@pytest.mark.asyncio
async def test_post_track_accepts_empty_properties(client):
    resp = await client.post("/api/track", json={
        "event": "form_start",
        "properties": {},
    })
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_post_track_stores_extra_fields_in_jsonb(client):
    resp = await client.post("/api/track", json={
        "event": "card_view",
        "properties": {
            "type_id": "01",
            "custom_field": "custom_value",
            "another_custom": 42,
        },
    })
    assert resp.status_code == 204

    from app.core.db import _ensure_engine
    session_maker = _ensure_engine()
    async with session_maker() as db:
        rows = (await db.execute(
            select(Event).where(Event.type_id == "01").order_by(Event.id.desc())
        )).scalars().all()
        latest = rows[0]
        assert latest.extra is not None
        assert latest.extra.get("custom_field") == "custom_value"
        assert latest.extra.get("another_custom") == 42
