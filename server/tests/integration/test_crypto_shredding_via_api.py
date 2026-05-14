"""End-to-end crypto-shredding test — goes through real HTTP API.

Unlike tests/integration/test_crypto_shredding.py (Plan 2, pure crypto +
direct ORM), this exercises: register (via API) → write encrypted chart
directly to DB → DELETE /api/auth/account (via API) → confirm:
  - dek_ciphertext is NULL in users
  - raw bytea ciphertext still present in charts
  - random DEK cannot decrypt it → InvalidTag
"""
from __future__ import annotations

import json
import os
import uuid

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .conftest import register_user


@pytest.mark.asyncio
async def test_shredding_via_api_makes_chart_ciphertext_irrecoverable(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, user = await register_user(client, phone)
    user_id = user["id"]

    # We need the user's DEK to write a test chart. In real life the DEK is
    # only available via current_user → decrypt_dek. Here we cheat: read the
    # ciphertext from DB, decrypt with the test KEK (which we do know, since
    # tests set it in os.environ).
    from app.core.crypto import decrypt_dek, encrypt_field, generate_dek
    from app.db_types import user_dek_context

    test_kek = bytes.fromhex(os.environ["ENCRYPTION_KEK"])

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as s:
        dek_ct = (await s.execute(text("""
            SELECT dek_ciphertext FROM users WHERE id = :uid
        """), {"uid": user_id})).scalar_one()

    dek = decrypt_dek(dek_ct, test_kek)

    # Insert a chart with encrypted birth_input using the DEK context.
    with user_dek_context(dek):
        async with maker() as s:
            from app.models.chart import Chart
            c = Chart(
                user_id=user_id,
                birth_input={"year": 1990, "month": 5, "day": 15},
                paipan={"sizhu": {"year": "庚午"}},
                engine_version="0.1.0",
            )
            s.add(c)
            await s.commit()
            chart_id = c.id

    # Confirm raw bytea is ciphertext (not plaintext).
    async with maker() as s:
        raw = (await s.execute(text("""
            SELECT birth_input FROM charts WHERE id = :cid
        """), {"cid": chart_id})).scalar_one()
    assert b"1990" not in raw
    assert len(raw) > 10

    # Now: DELETE /api/auth/account via HTTP.
    r = await client.request(
        "DELETE",
        "/api/auth/account",
        cookies={"session": cookie},
        json={"confirm": "DELETE MY ACCOUNT"},
    )
    assert r.status_code == 200

    # Confirm users.dek_ciphertext is NULL.
    async with maker() as s:
        dek_ct_after = (await s.execute(text("""
            SELECT dek_ciphertext FROM users WHERE id = :uid
        """), {"uid": user_id})).scalar_one()
    assert dek_ct_after is None

    # Confirm charts.birth_input STILL has the ciphertext (not deleted).
    async with maker() as s:
        raw_after = (await s.execute(text("""
            SELECT birth_input FROM charts WHERE id = :cid
        """), {"cid": chart_id})).scalar_one()
    assert raw_after == raw    # ciphertext unchanged — just the KEY is gone

    # Random DEK must fail decryption.
    random_dek = generate_dek()
    from app.core.crypto import decrypt_field
    with pytest.raises(InvalidTag):
        decrypt_field(raw_after, random_dek)

    # Original DEK would still work (positive control). But the user can't
    # retrieve it anymore because dek_ciphertext is NULL.
    recovered = json.loads(decrypt_field(raw_after, dek).decode("utf-8"))
    assert recovered["year"] == 1990

    await engine.dispose()


@pytest.mark.asyncio
async def test_shredded_user_cookie_is_401(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)

    await client.request(
        "DELETE",
        "/api/auth/account",
        cookies={"session": cookie},
        json={"confirm": "DELETE MY ACCOUNT"},
    )

    r = await client.get("/api/auth/me", cookies={"session": cookie})
    assert r.status_code == 401
    # Session row was deleted, so "SESSION_INVALID" — not "ACCOUNT_SHREDDED"
    # (the shredded branch is only reachable if the session survived, which
    # it doesn't because shred_account calls revoke_all_sessions).
