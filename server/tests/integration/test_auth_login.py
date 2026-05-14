"""Integration tests for POST /api/auth/login."""
from __future__ import annotations

import hashlib
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .conftest import register_user


async def _send_login_sms(client, phone):
    """Insert a fresh login SMS code directly (bypasses 60s cooldown).

    The register flow already issued a 'register' SMS for this phone; the 60s
    cross-purpose cooldown would block an immediate /sms/send API call. Inserting
    directly matches what a test needs: a known-good code attached to the phone.
    """
    code = f"{uuid.uuid4().int % 1_000_000:06d}"
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(
            text(
                """
                INSERT INTO sms_codes (phone, code_hash, purpose, expires_at, created_at)
                VALUES (:p, :h, 'login',
                        now() + interval '5 minutes',
                        now() - interval '2 minutes')
                """
            ),
            {"p": phone, "h": code_hash},
        )
        await s.commit()
    await engine.dispose()
    return code


@pytest.mark.asyncio
async def test_login_full_flow(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    await register_user(client, phone)

    code = await _send_login_sms(client, phone)
    r = await client.post("/api/auth/login", json={"phone": phone, "code": code})
    assert r.status_code == 200
    assert r.cookies.get("session") is not None
    assert r.json()["user"]["phone_last4"] == phone[-4:]


@pytest.mark.asyncio
async def test_login_unregistered_phone(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    code = await _send_login_sms(client, phone)
    r = await client.post("/api/auth/login", json={"phone": phone, "code": code})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "USER_NOT_FOUND"


@pytest.mark.asyncio
async def test_login_wrong_code(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    await register_user(client, phone)
    await _send_login_sms(client, phone)
    r = await client.post("/api/auth/login", json={"phone": phone, "code": "000000"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "SMS_CODE_INVALID"


@pytest.mark.asyncio
async def test_login_disabled_account(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    _, user = await register_user(client, phone)

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text("UPDATE users SET status='disabled' WHERE id=:uid"),
                         {"uid": user["id"]})
        await s.commit()
    await engine.dispose()

    code = await _send_login_sms(client, phone)
    r = await client.post("/api/auth/login", json={"phone": phone, "code": code})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "ACCOUNT_DISABLED"


@pytest.mark.asyncio
async def test_login_preserves_existing_sessions(client):
    """Login creates a NEW session; existing sessions remain valid."""
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie1, _ = await register_user(client, phone)

    code = await _send_login_sms(client, phone)
    r = await client.post("/api/auth/login", json={"phone": phone, "code": code})
    cookie2 = r.cookies.get("session")

    assert cookie1 != cookie2
    # Both cookies can access /me
    r1 = await client.get("/api/auth/me", cookies={"session": cookie1})
    r2 = await client.get("/api/auth/me", cookies={"session": cookie2})
    assert r1.status_code == 200
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_login_phone_invalid_format(client):
    r = await client.post("/api/auth/login", json={"phone": "abc", "code": "123456"})
    assert r.status_code == 422
