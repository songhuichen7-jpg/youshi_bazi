"""Integration tests for GET / DELETE /api/auth/sessions."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .conftest import register_user


async def _send_login_sms_via_db(phone: str) -> str:
    """Insert a login SMS code directly (bypasses 60s cooldown for tests)."""
    import hashlib
    code = "654321"
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text("""
            INSERT INTO sms_codes (phone, code_hash, purpose, expires_at, created_at)
            VALUES (:p, :h, 'login', now() + interval '5 minutes', now() - interval '2 minutes')
        """), {"p": phone, "h": code_hash})
        await s.commit()
    await engine.dispose()
    return code


@pytest.mark.asyncio
async def test_list_sessions_shows_current(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    r = await client.get("/api/auth/sessions", cookies={"session": cookie})
    assert r.status_code == 200
    sessions = r.json()
    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True


@pytest.mark.asyncio
async def test_list_sessions_requires_auth(client):
    r = await client.get("/api/auth/sessions")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_revoke_own_session(client):
    """Login twice; revoke the non-current session."""
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie1, _ = await register_user(client, phone)

    # Second login via direct SMS insert (sidesteps cooldown).
    code = await _send_login_sms_via_db(phone)
    r = await client.post("/api/auth/login", json={"phone": phone, "code": code})
    cookie2 = r.cookies.get("session")

    # List via cookie1; find cookie2's session id.
    r = await client.get("/api/auth/sessions", cookies={"session": cookie1})
    sessions = r.json()
    other_session_id = next(s["id"] for s in sessions if not s["is_current"])

    r = await client.delete(f"/api/auth/sessions/{other_session_id}",
                              cookies={"session": cookie1})
    assert r.status_code == 204

    # cookie2 must now 401.
    r = await client.get("/api/auth/me", cookies={"session": cookie2})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_revoke_current_session_clears_cookie(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    r = await client.get("/api/auth/sessions", cookies={"session": cookie})
    current_id = r.json()[0]["id"]

    r = await client.delete(f"/api/auth/sessions/{current_id}", cookies={"session": cookie})
    assert r.status_code == 204

    # Cookie cleared; subsequent call without explicit cookie must 401.
    r = await client.get("/api/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_revoke_other_users_session_returns_404(client):
    """Privacy: revoking another user's session must 404, not 403."""
    phone_a = f"+86138{uuid.uuid4().int % 10**8:08d}"
    phone_b = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie_a, _ = await register_user(client, phone_a)
    cookie_b, _ = await register_user(client, phone_b)

    # B lists their session to get the id.
    r = await client.get("/api/auth/sessions", cookies={"session": cookie_b})
    b_session_id = r.json()[0]["id"]

    # A tries to revoke B's session.
    r = await client.delete(f"/api/auth/sessions/{b_session_id}",
                              cookies={"session": cookie_a})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "SESSION_NOT_FOUND"
