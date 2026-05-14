"""PATCH /api/auth/me cascades nickname change to hepan_invites snapshots
and writes onboarded_at when mark_onboarded=True."""
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

    Returns the slug of the completed hepan invite. Mirrors the helper in
    ``test_hepan_reading_gate.py`` but takes the caller's cookie so the test
    can rename the same A and observe the cascade.
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


async def test_patch_me_cascades_nickname_to_hepan_invites(client):
    """When A renames, hepan_invites.a_nickname snapshot updates in same txn."""
    phone = await _new_phone()
    cookie, user = await register_user(client, phone)
    # standard plan so /api/hepan/invite is allowed.
    await upgrade_user_plan(user["id"], "standard")
    slug = await _setup_completed_hepan_for_user(client, cookie)

    # Sanity: snapshot is the original "小夜灯" before rename.
    mine_before = await client.get("/api/hepan/mine", cookies={"session": cookie})
    assert mine_before.status_code == 200
    bound_before = [it for it in mine_before.json()["items"] if it["slug"] == slug]
    assert bound_before and bound_before[0]["a_nickname"] == "小夜灯"

    # Rename A
    resp = await client.patch(
        "/api/auth/me",
        json={"nickname": "新名字"},
        cookies={"session": cookie},
    )
    assert resp.status_code == 200
    assert resp.json()["nickname"] == "新名字"

    # Hepan list should reflect the new a_nickname
    mine = await client.get("/api/hepan/mine", cookies={"session": cookie})
    assert mine.status_code == 200
    items = mine.json()["items"]
    bound = [it for it in items if it["slug"] == slug]
    assert bound and bound[0]["a_nickname"] == "新名字"


async def test_patch_me_mark_onboarded_writes_timestamp(client):
    """mark_onboarded=True alone (without nickname/avatar) sets onboarded_at."""
    phone = await _new_phone()
    cookie, _ = await register_user(client, phone)

    me_before = await client.get("/api/auth/me", cookies={"session": cookie})
    assert me_before.json()["user"]["onboarded_at"] is None

    resp = await client.patch(
        "/api/auth/me",
        json={"mark_onboarded": True},
        cookies={"session": cookie},
    )
    assert resp.status_code == 200
    assert resp.json()["onboarded_at"] is not None

    me_after = await client.get("/api/auth/me", cookies={"session": cookie})
    assert me_after.json()["user"]["onboarded_at"] is not None


async def test_patch_me_idempotent_mark_onboarded(client):
    """Calling mark_onboarded=True a second time keeps the original timestamp."""
    phone = await _new_phone()
    cookie, _ = await register_user(client, phone)

    r1 = await client.patch(
        "/api/auth/me",
        json={"mark_onboarded": True},
        cookies={"session": cookie},
    )
    ts1 = r1.json()["onboarded_at"]

    r2 = await client.patch(
        "/api/auth/me",
        json={"mark_onboarded": True},
        cookies={"session": cookie},
    )
    ts2 = r2.json()["onboarded_at"]

    assert ts1 == ts2  # not overwritten on subsequent calls
