"""POST /api/hepan/{slug}/reading is creator-only — non-creator B gets 404.

Regression for Task 25: previously the endpoint only checked slug existence
and soft-delete, so any logged-in user with the slug could trigger reading
generation on someone else's hepan. The endpoint now uses
``_load_creator_invite`` like the chat endpoints, raising 404 on
``row.user_id != user.id``.

Crucially, the 404 fires BEFORE the lite-plan paywall hint so non-creator B
gets no information leak about endpoint existence — even when B is on lite.
"""
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


async def _setup_completed_hepan_for_user(
    client, *, plan: str = "standard"
) -> tuple[str, str]:
    """Register A, optionally upgrade plan, run A-invites + B-completes flow.

    Returns ``(a_cookie, slug)``.
    """
    phone = f"+86137{uuid.uuid4().int % 10**8:08d}"
    cookie, user = await register_user(client, phone)
    if plan != "lite":
        await upgrade_user_plan(user["id"], plan)

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
    return cookie, slug


async def test_non_creator_gets_404_on_reading(client):
    """B (different account) hitting A's reading endpoint → 404, not 402."""
    _, slug = await _setup_completed_hepan_for_user(client, plan="standard")

    # B logs in with a different cookie + a different invite code.
    b_phone = f"+86139{uuid.uuid4().int % 10**8:08d}"
    b_cookie, b_user = await register_user(client, b_phone)
    # Upgrade B to standard so the 404 isn't masked by the lite paywall;
    # creator gate must fire before plan check anyway, but this makes the
    # information-leak assertion crisp regardless of gate ordering.
    await upgrade_user_plan(b_user["id"], "standard")

    resp = await client.post(
        f"/api/hepan/{slug}/reading",
        cookies={"session": b_cookie},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "invite not found"


async def test_non_creator_lite_user_gets_404_not_402(client):
    """Even a lite-plan B sees 404, NOT 402 paywall — no endpoint-existence leak.

    This is the actual security property: gate ordering must put the
    creator-only check ahead of the plan gate, so an attacker on lite can't
    learn "this slug has a reading endpoint, just upgrade".
    """
    _, slug = await _setup_completed_hepan_for_user(client, plan="standard")

    # B is a fresh account → defaults to lite plan.
    b_phone = f"+86139{uuid.uuid4().int % 10**8:08d}"
    b_cookie, _ = await register_user(client, b_phone)

    resp = await client.post(
        f"/api/hepan/{slug}/reading",
        cookies={"session": b_cookie},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "invite not found"


async def test_creator_post_reading_not_404(client):
    """Sanity: A's own POST is not blocked by the new gate.

    May still return non-200 (402 paywall, 409 not-completed, or upstream LLM
    issues), but specifically not the 404 we just added.
    """
    a_cookie, slug = await _setup_completed_hepan_for_user(client, plan="standard")

    resp = await client.post(
        f"/api/hepan/{slug}/reading",
        cookies={"session": a_cookie},
    )
    # The creator gate should NOT fire — anything else (200/409/500/etc.) is OK
    # for this test. We're checking only that the new 404 path is not hit.
    assert resp.status_code != 404, (
        f"creator unexpectedly got 404 from reading endpoint: {resp.text}"
    )


async def test_non_creator_lite_user_gets_404_on_messages_not_402(client):
    """B (lite plan) hitting A's messages endpoint → 404, NOT 402 paywall.

    Mirrors test_non_creator_lite_user_gets_404_not_402 but for the chat
    POST /{slug}/messages endpoint. Same security property: gate ordering
    must put the creator-only check ahead of the plan gate.
    """
    _, slug = await _setup_completed_hepan_for_user(client, plan="standard")

    # B is a fresh account → defaults to lite plan.
    b_phone = f"+86139{uuid.uuid4().int % 10**8:08d}"
    b_cookie, _ = await register_user(client, b_phone)

    resp = await client.post(
        f"/api/hepan/{slug}/messages",
        cookies={"session": b_cookie},
        json={"message": "你好"},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "invite not found"


async def test_non_creator_standard_user_gets_404_on_messages(client):
    """B (standard plan, different account) hitting A's messages endpoint → 404.

    Sanity check that the creator-gate works regardless of plan, so the
    information-leak fix doesn't accidentally regress in either direction.
    """
    _, slug = await _setup_completed_hepan_for_user(client, plan="standard")

    b_phone = f"+86139{uuid.uuid4().int % 10**8:08d}"
    b_cookie, b_user = await register_user(client, b_phone)
    await upgrade_user_plan(b_user["id"], "standard")

    resp = await client.post(
        f"/api/hepan/{slug}/messages",
        cookies={"session": b_cookie},
        json={"message": "你好"},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "invite not found"


async def _seed_reading_text_for_slug(slug: str) -> None:
    """Directly write an encrypted reading_text on the hepan row, using A's DEK.

    Bypasses the LLM stream — purely a DB-level seed so the regression test
    doesn't depend on a configured LLM key. Encrypts with A's DEK so it's
    "valid" ciphertext that the owner could decrypt; B's DEK won't.
    """
    import os

    from sqlalchemy import text as sql_text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.crypto import decrypt_dek, encrypt_field, load_kek

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as s:
            row = (await s.execute(
                sql_text(
                    """
                    SELECT u.dek_ciphertext
                      FROM hepan_invites hi
                      JOIN users u ON u.id = hi.user_id
                     WHERE hi.slug = :slug
                    """
                ),
                {"slug": slug},
            )).one()
            kek = load_kek()
            dek = decrypt_dek(bytes(row.dek_ciphertext), kek)
            ciphertext = encrypt_field(b"fake reading text for test", dek)
            await s.execute(
                sql_text(
                    """
                    UPDATE hepan_invites
                       SET reading_text = :ct,
                           reading_version = :v,
                           reading_generated_at = NOW()
                     WHERE slug = :slug
                    """
                ),
                {"ct": ciphertext, "v": "test-v1", "slug": slug},
            )
            await s.commit()
    finally:
        await engine.dispose()


async def test_non_creator_gets_404_not_500_when_reading_generated(client):
    """Regression: when A's hepan already has a generated reading_text,
    B's POST /reading must still return 404 — not a 500 from DEK mismatch
    on the undeferred reading_text column.

    Pre-fix flow: SELECT(undefer(reading_text)) ran first, ORM tried to
    decrypt with B's DEK, InvalidTag, 500. Post-fix: WHERE user_id=B
    filters the row out at SQL level — no decryption attempted.
    """
    # A: create + complete hepan, then seed reading_text via direct DB write
    # (deterministic — no LLM key required in test env).
    _, slug = await _setup_completed_hepan_for_user(client, plan="standard")
    await _seed_reading_text_for_slug(slug)

    # B tries to read — must be 404, not 500 (InvalidTag from DEK mismatch).
    b_phone = f"+86139{uuid.uuid4().int % 10**8:08d}"
    b_cookie, b_user = await register_user(client, b_phone)
    await upgrade_user_plan(b_user["id"], "standard")

    resp = await client.post(
        f"/api/hepan/{slug}/reading",
        cookies={"session": b_cookie},
    )
    assert resp.status_code == 404, (
        f"expected 404, got {resp.status_code}. Body: {resp.text[:200]}"
    )
    assert resp.json().get("detail") == "invite not found"


async def test_non_creator_gets_404_not_500_on_messages_when_reading_generated(
    client,
):
    """Same regression as above but for the chat /messages endpoint.

    Both endpoints use _load_creator_invite, so the SQL-level WHERE filter
    must protect both from DEK-mismatch 500s.
    """
    _, slug = await _setup_completed_hepan_for_user(client, plan="standard")
    await _seed_reading_text_for_slug(slug)

    b_phone = f"+86139{uuid.uuid4().int % 10**8:08d}"
    b_cookie, b_user = await register_user(client, b_phone)
    await upgrade_user_plan(b_user["id"], "standard")

    resp = await client.post(
        f"/api/hepan/{slug}/messages",
        cookies={"session": b_cookie},
        json={"message": "你好"},
    )
    assert resp.status_code == 404, (
        f"expected 404, got {resp.status_code}. Body: {resp.text[:200]}"
    )
    assert resp.json().get("detail") == "invite not found"
