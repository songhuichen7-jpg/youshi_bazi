"""Integration tests for POST /api/auth/logout."""
from __future__ import annotations

import uuid

import pytest

from .conftest import register_user


@pytest.mark.asyncio
async def test_logout_clears_cookie_and_blocks_future_calls(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)

    r = await client.post("/api/auth/logout", cookies={"session": cookie})
    assert r.status_code == 200
    # Subsequent call with the same cookie must fail (session row deleted)
    r = await client.get("/api/auth/me", cookies={"session": cookie})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_requires_auth(client):
    r = await client.post("/api/auth/logout")
    assert r.status_code == 401
