"""Integration: conversation create/list round-trips hepan_slug."""
from __future__ import annotations

import uuid

import pytest
from tests.integration.conftest import register_user


pytestmark = pytest.mark.asyncio


async def _register_with_chart(client) -> tuple[str, str]:
    """Returns (session_cookie, chart_id)."""
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    r = await client.post("/api/charts", cookies={"session": cookie}, json={
        "birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"},
    })
    assert r.status_code == 201, r.text
    return cookie, r.json()["chart"]["id"]


async def _create_completed_hepan(client, cookie: str) -> str:
    """Run the A-invites + B-completes flow; return the slug."""
    invite_resp = await client.post(
        "/api/hepan/invite",
        cookies={"session": cookie},
        json={
            "birth": {
                "year": 2003,
                "month": 8,
                "day": 29,
                "hour": 8,
                "minute": 25,
                "city": "长沙",
                "gender": "male",
                "useTrueSolarTime": True,
                "ziConvention": "early",
            },
            "nickname": "小夜灯",
        },
    )
    assert invite_resp.status_code == 200, invite_resp.text
    slug = invite_resp.json()["slug"]

    complete_resp = await client.post(
        f"/api/hepan/{slug}/complete",
        json={
            "birth": {
                "year": 2001,
                "month": 2,
                "day": 3,
                "hour": 9,
                "minute": 10,
                "city": "杭州",
                "gender": "female",
                "useTrueSolarTime": True,
                "ziConvention": "early",
            },
            "nickname": "多肉",
        },
    )
    assert complete_resp.status_code == 200, complete_resp.text
    return slug


async def test_create_conversation_with_hepan_slug(client):
    """POST /conversations with hepan_slug stores it; GET list returns it."""
    cookie, chart_id = await _register_with_chart(client)
    slug = await _create_completed_hepan(client, cookie)

    resp = await client.post(
        f"/api/charts/{chart_id}/conversations",
        cookies={"session": cookie},
        json={"label": "合盘 · A × B", "hepan_slug": slug},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["hepan_slug"] == slug
    assert body["label"] == "合盘 · A × B"

    list_resp = await client.get(
        f"/api/charts/{chart_id}/conversations",
        cookies={"session": cookie},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    bound = [i for i in items if i["id"] == body["id"]]
    assert bound and bound[0]["hepan_slug"] == slug


async def test_create_conversation_without_hepan_slug(client):
    """Existing path: omit hepan_slug → null in DB and response."""
    cookie, chart_id = await _register_with_chart(client)
    resp = await client.post(
        f"/api/charts/{chart_id}/conversations",
        cookies={"session": cookie},
        json={"label": "对话 1"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["hepan_slug"] is None
