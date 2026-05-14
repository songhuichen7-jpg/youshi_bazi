"""GET /api/hepan/mine and /api/hepan/{slug} return current avatar_url
(JOINed from users table, not snapshotted)."""
from __future__ import annotations

import uuid

import pytest

from tests.integration.conftest import register_user, upgrade_user_plan


pytestmark = pytest.mark.asyncio


_A_BIRTH = {
    "year": 2003,
    "month": 8,
    "day": 29,
    "hour": 8,
    "minute": 25,
    "city": "长沙",
    "gender": "male",
    "useTrueSolarTime": True,
    "ziConvention": "early",
}

_B_BIRTH = {
    "year": 2001,
    "month": 2,
    "day": 3,
    "hour": 9,
    "minute": 10,
    "city": "杭州",
    "gender": "female",
    "useTrueSolarTime": True,
    "ziConvention": "early",
}


async def _new_phone() -> str:
    return f"+86137{uuid.uuid4().int % 10**8:08d}"


async def _setup_completed_hepan_for_user(client, cookie: str) -> str:
    """Run A-invites + B-completes flow against an existing logged-in cookie.

    Mirrors the helper in ``test_profile_cascade.py``.
    """
    invite_resp = await client.post(
        "/api/hepan/invite",
        cookies={"session": cookie},
        json={"birth": _A_BIRTH, "nickname": "小夜灯"},
    )
    assert invite_resp.status_code == 200, invite_resp.text
    slug = invite_resp.json()["slug"]

    complete_resp = await client.post(
        f"/api/hepan/{slug}/complete",
        json={"birth": _B_BIRTH, "nickname": "多肉"},
    )
    assert complete_resp.status_code == 200, complete_resp.text
    return slug


async def test_mine_returns_avatar_url_field(client):
    phone = await _new_phone()
    cookie, user = await register_user(client, phone)
    await upgrade_user_plan(user["id"], "standard")
    slug = await _setup_completed_hepan_for_user(client, cookie)

    mine = await client.get("/api/hepan/mine", cookies={"session": cookie})
    assert mine.status_code == 200
    items = mine.json()["items"]
    bound = next(it for it in items if it["slug"] == slug)
    assert "a_avatar_url" in bound
    assert "b_avatar_url" in bound
    # No avatar uploaded yet, so values are None
    assert bound["a_avatar_url"] is None
    assert bound["b_avatar_url"] is None


async def test_slug_response_returns_avatar_url(client):
    phone = await _new_phone()
    cookie, user = await register_user(client, phone)
    await upgrade_user_plan(user["id"], "standard")
    slug = await _setup_completed_hepan_for_user(client, cookie)

    resp = await client.get(f"/api/hepan/{slug}", cookies={"session": cookie})
    assert resp.status_code == 200
    body = resp.json()
    assert "avatar_url" in body["a"]
    assert body["a"]["avatar_url"] is None  # no upload yet
    if body.get("b"):
        assert "avatar_url" in body["b"]


async def test_avatar_url_is_live_not_snapshot(client):
    """After A sets avatar_url, /mine reflects it without re-completing the hepan."""
    phone = await _new_phone()
    cookie, user = await register_user(client, phone)
    await upgrade_user_plan(user["id"], "standard")
    slug = await _setup_completed_hepan_for_user(client, cookie)

    # Set avatar_url directly via PATCH /me
    resp = await client.patch(
        "/api/auth/me",
        json={"avatar_url": "/static/avatars/test.webp"},
        cookies={"session": cookie},
    )
    assert resp.status_code == 200, resp.text

    mine = await client.get("/api/hepan/mine", cookies={"session": cookie})
    items = mine.json()["items"]
    bound = next(it for it in items if it["slug"] == slug)
    assert bound["a_avatar_url"] == "/static/avatars/test.webp"
