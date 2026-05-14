"""Integration tests for app.auth.deps real implementations.

Exercises current_user / optional_user / require_admin / check_quota end-to-end
through the actual FastAPI app + testcontainers Postgres.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace
import uuid

import pytest
import pytest_asyncio
from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDb:
    def __init__(self, session_row, user):
        self.session_row = session_row
        self.user = user
        self.execute_calls = []
        self.commit_calls = 0

    async def execute(self, statement, params=None):
        self.execute_calls.append((str(statement), params))
        if len(self.execute_calls) == 1:
            return _ScalarResult(self.session_row)
        return _ScalarResult(None)

    async def get(self, model, user_id):
        return self.user

    async def commit(self):
        self.commit_calls += 1


@pytest_asyncio.fixture
async def client(database_url, monkeypatch):
    """Fresh client per test — forces lifespan / KEK / app.state.kek wiring.

    Also wires the app's module-level engine singleton to the testcontainers
    Postgres URL so get_db() dependencies resolve against the real DB.
    """
    import importlib
    import sys

    # Make sure any code path that re-reads settings sees the real DB URL.
    monkeypatch.setenv("DATABASE_URL", str(database_url))
    # "dev" env makes /api/auth/sms/send echo the OTP in the response (__devCode)
    # so the test can complete the register flow without scraping the DB.
    monkeypatch.setenv("ENV", "dev")

    cfg_mod = sys.modules.get("app.core.config")
    if cfg_mod is not None:
        importlib.reload(cfg_mod)

    # Reset the engine singleton — its next access will rebuild against the
    # reloaded settings.database_url (pointing at the testcontainer).
    from app.core import db as db_mod
    await db_mod.dispose_engine()

    main_mod = sys.modules.get("app.main")
    if main_mod is not None:
        importlib.reload(main_mod)
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            yield c

    await db_mod.dispose_engine()


async def _register_and_get_cookie(client: AsyncClient, phone: str) -> tuple[str, dict]:
    """Helper: register user with dev SMS; returns (cookie_value, user_dict)."""
    # Seed an invite code via direct DB (we don't have admin routes yet).
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy import text
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        # Bootstrap user (creator of the invite code) with random phone.
        bootstrap_phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
        await s.execute(text("""
            INSERT INTO users (phone, phone_last4, dek_ciphertext, dek_key_version)
            VALUES (:phone, :last4, :ct, 1)
        """), {"phone": bootstrap_phone, "last4": bootstrap_phone[-4:],
                "ct": b"\x00" * 44})
        bootstrap_id = (await s.execute(text("""
            SELECT id FROM users WHERE phone=:p
        """), {"p": bootstrap_phone})).scalar_one()
        invite = f"INV-{uuid.uuid4().hex[:8].upper()}"
        await s.execute(text("""
            INSERT INTO invite_codes (code, created_by, max_uses) VALUES (:c, :u, 10)
        """), {"c": invite, "u": bootstrap_id})
        await s.commit()
    await engine.dispose()

    # 1. SMS send → dev code in response
    r = await client.post("/api/auth/sms/send", json={"phone": phone, "purpose": "register"})
    assert r.status_code == 200, r.text
    code = r.json()["__devCode"]

    # 2. register
    r = await client.post("/api/auth/register", json={
        "phone": phone, "code": code, "invite_code": invite,
        "nickname": "test", "agreed_to_terms": True,
    })
    assert r.status_code == 200, r.text
    cookie = r.cookies.get("session")
    assert cookie, "session cookie not set"
    user = r.json()["user"]
    return cookie, user


@pytest.mark.asyncio
async def test_current_user_blocks_no_cookie(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_current_user_blocks_bogus_cookie(client):
    r = await client.get("/api/auth/me", cookies={"session": "not-a-real-token"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "SESSION_INVALID"


@pytest.mark.asyncio
async def test_current_user_valid_cookie(client):
    cookie, user = await _register_and_get_cookie(client, "+8613811110001")
    r = await client.get("/api/auth/me", cookies={"session": cookie})
    assert r.status_code == 200
    assert r.json()["user"]["id"] == user["id"]
    assert r.json()["user"]["phone_last4"] == "0001"
    # phone full value must NOT appear
    assert "phone" not in r.json()["user"]


@pytest.mark.asyncio
async def test_authenticate_commits_session_touch_before_business_handler(client, monkeypatch):
    """Release the sessions row lock before long-running handlers execute."""
    import app.auth.deps as deps_mod

    monkeypatch.setattr(deps_mod, "decrypt_dek", lambda ciphertext, kek: b"test-dek")

    session_row = SimpleNamespace(
        id="session-id",
        user_id="user-id",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    user = SimpleNamespace(
        id="user-id",
        status="active",
        dek_ciphertext=b"ciphertext",
    )
    db = _FakeDb(session_row=session_row, user=user)
    request = SimpleNamespace(
        cookies={"session": "session-token"},
        app=SimpleNamespace(state=SimpleNamespace(kek=b"kek")),
        state=SimpleNamespace(),
    )

    _, dek_token = await deps_mod._authenticate_and_mount_dek(request, db)
    try:
        assert db.commit_calls == 1
    finally:
        deps_mod._current_dek.reset(dek_token)


@pytest.mark.asyncio
async def test_current_user_treats_bad_dek_as_expired_session(monkeypatch):
    """A stale local DB / changed KEK must not turn chart bootstrap into HTTP 500."""
    import app.auth.deps as deps_mod

    def _raise_invalid_tag(ciphertext, kek):
        raise InvalidTag

    monkeypatch.setattr(deps_mod, "decrypt_dek", _raise_invalid_tag)

    session_row = SimpleNamespace(
        id="session-id",
        user_id="user-id",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    user = SimpleNamespace(
        id="user-id",
        status="active",
        dek_ciphertext=b"ciphertext",
    )
    db = _FakeDb(session_row=session_row, user=user)
    request = SimpleNamespace(
        cookies={"session": "session-token"},
        app=SimpleNamespace(state=SimpleNamespace(kek=b"kek")),
        state=SimpleNamespace(),
    )

    with pytest.raises(HTTPException) as exc:
        await deps_mod._authenticate_and_mount_dek(request, db)

    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == "SESSION_CRYPTO_INVALID"
    assert db.commit_calls == 0


@pytest.mark.asyncio
async def test_phone_full_value_never_in_response(client):
    cookie, _ = await _register_and_get_cookie(client, "+8613811110002")
    r = await client.get("/api/auth/me", cookies={"session": cookie})
    assert "+8613811110002" not in r.text
    assert "13811110002" not in r.text


@pytest.mark.asyncio
async def test_current_user_yield_dep_calls_reset_on_teardown(client, monkeypatch):
    """Task 3 (cleanup): yield-dep finally-block must call _current_dek.reset.

    Structural test: wraps _current_dek in a spy in app.auth.deps, hits /api/auth/me
    (which depends on current_user), and verifies reset was called."""
    import uuid
    from contextvars import ContextVar
    from app.db_types import _current_dek
    import app.auth.deps as deps_mod
    from tests.integration.conftest import register_user

    reset_calls = []
    original_dek = deps_mod._current_dek

    class _SpyContextVar:
        """Thin wrapper that records .reset() calls, forwarding to the real ContextVar."""

        def get(self, default=None):
            return original_dek.get(default)

        def set(self, value):
            return original_dek.set(value)

        def reset(self, token):
            reset_calls.append(token)
            return original_dek.reset(token)

    monkeypatch.setattr(deps_mod, "_current_dek", _SpyContextVar())

    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)

    r = await client.get("/api/auth/me", cookies={"session": cookie})
    assert r.status_code == 200

    # At least one reset should have happened during the GET /api/auth/me request
    # (current_user's yield-dep finally block)
    assert len(reset_calls) >= 1, "_current_dek.reset should be called after current_user yield"


@pytest.mark.asyncio
async def test_dek_contextvar_clean_after_request(client):
    """Task 3 (cleanup): after a request that sets DEK, the contextvar in the
    test task is not leaking (per-task isolation + proper reset)."""
    import uuid
    from app.db_types import _current_dek
    from tests.integration.conftest import register_user

    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    await client.get("/api/auth/me", cookies={"session": cookie})

    # In the test's own asyncio task, the contextvar should not have any leaked value.
    # (Each request runs in its own task, so even without reset this would be None;
    # but with reset, the invariant is stronger.)
    assert _current_dek.get(None) is None


@pytest.mark.asyncio
async def test_authenticate_helper_resets_dek_on_post_set_failure(client, monkeypatch):
    """Important #1 (cleanup review): if db.execute raises AFTER _current_dek.set,
    the contextvar must still be reset before the exception propagates.

    Simulates a DB failure on the rolling-expiry UPDATE by monkey-patching
    AsyncSession.execute to raise after the set. Then asserts the
    contextvar is not leaked (reset() was called).
    """
    import uuid
    import app.auth.deps as deps_mod
    from tests.integration.conftest import register_user

    # Register a user so we have a valid session cookie
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)

    # Use the same _SpyContextVar pattern as test_current_user_yield_dep_calls_reset_on_teardown
    reset_calls = []
    original_dek = deps_mod._current_dek

    class _SpyContextVar:
        """Thin wrapper that records .reset() calls, forwarding to the real ContextVar."""

        def get(self, default=None):
            return original_dek.get(default)

        def set(self, value):
            return original_dek.set(value)

        def reset(self, token):
            reset_calls.append(token)
            return original_dek.reset(token)

    monkeypatch.setattr(deps_mod, "_current_dek", _SpyContextVar())

    # Force the rolling-expiry UPDATE to fail by monkey-patching AsyncSession.execute.
    # Only fail on the specific UPDATE; let other queries (SELECT user, SELECT session) pass.
    from sqlalchemy.ext.asyncio import AsyncSession
    real_execute = AsyncSession.execute

    async def _fail_on_session_update(self, statement, params=None, *a, **kw):
        sql = str(statement)
        if "UPDATE sessions" in sql and "last_seen_at" in sql:
            raise RuntimeError("simulated DB error on session touch")
        return await real_execute(self, statement, params, *a, **kw)

    monkeypatch.setattr(AsyncSession, "execute", _fail_on_session_update)

    # Hit any route that uses current_user. ASGITransport may propagate unhandled
    # server-side exceptions directly to the test; catch either outcome.
    try:
        r = await client.get("/api/auth/me", cookies={"session": cookie})
        # If FastAPI caught it and returned a 500, that's fine too.
        assert r.status_code in (500, 503)
    except RuntimeError as exc:
        assert "simulated DB error" in str(exc), f"unexpected error: {exc}"

    # The reset MUST have been called even though the request failed
    assert len(reset_calls) >= 1, "reset must be called even when post-set db.execute fails"
