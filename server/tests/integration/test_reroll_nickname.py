"""POST /api/auth/me/reroll-nickname picks a new pool name (≠ current)."""
from __future__ import annotations

import uuid

import pytest

from app.services.nickname_pool import NICKNAMES
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

    Returns the slug of the completed hepan invite. Mirrors the helper in
    ``test_profile_cascade.py`` so the reroll test can rename the same A and
    observe the cascade.
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


async def test_reroll_returns_pool_member_not_current(client):
    phone = await _new_phone()
    cookie, _ = await register_user(client, phone)
    me = await client.get("/api/auth/me", cookies={"session": cookie})
    current = me.json()["user"]["nickname"]

    resp = await client.post(
        "/api/auth/me/reroll-nickname",
        cookies={"session": cookie},
    )
    assert resp.status_code == 200
    new_nick = resp.json()["nickname"]
    assert new_nick in NICKNAMES
    assert new_nick != current


async def test_reroll_persists_to_user_row(client):
    phone = await _new_phone()
    cookie, _ = await register_user(client, phone)
    resp = await client.post(
        "/api/auth/me/reroll-nickname",
        cookies={"session": cookie},
    )
    new_nick = resp.json()["nickname"]

    me = await client.get("/api/auth/me", cookies={"session": cookie})
    assert me.json()["user"]["nickname"] == new_nick


async def test_reroll_cascades_to_hepan_invites(client):
    """Reroll counts as a nickname change — hepan_invites snapshot updates."""
    phone = await _new_phone()
    cookie, user = await register_user(client, phone)
    # standard plan so /api/hepan/invite is allowed.
    await upgrade_user_plan(user["id"], "standard")
    slug = await _setup_completed_hepan_for_user(client, cookie)

    resp = await client.post(
        "/api/auth/me/reroll-nickname",
        cookies={"session": cookie},
    )
    new_nick = resp.json()["nickname"]

    mine = await client.get("/api/hepan/mine", cookies={"session": cookie})
    items = mine.json()["items"]
    bound = [it for it in items if it["slug"] == slug]
    assert bound and bound[0]["a_nickname"] == new_nick
