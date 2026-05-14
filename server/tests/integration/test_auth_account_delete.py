"""Integration tests for DELETE /api/auth/account — crypto-shredding."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .conftest import register_user


@pytest.mark.asyncio
async def test_delete_account_full_flow(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)

    r = await client.request(
        "DELETE",
        "/api/auth/account",
        cookies={"session": cookie},
        json={"confirm": "DELETE MY ACCOUNT"},
    )
    assert r.status_code == 200
    assert "shredded_at" in r.json()


@pytest.mark.asyncio
async def test_delete_account_wrong_confirm(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)

    r = await client.request(
        "DELETE",
        "/api/auth/account",
        cookies={"session": cookie},
        json={"confirm": "delete my account"},  # wrong case
    )
    assert r.status_code == 422   # Pydantic Literal match failure


@pytest.mark.asyncio
async def test_delete_account_sets_dek_null(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, user = await register_user(client, phone)

    await client.request(
        "DELETE",
        "/api/auth/account",
        cookies={"session": cookie},
        json={"confirm": "DELETE MY ACCOUNT"},
    )

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        row = (await s.execute(text("""
            SELECT dek_ciphertext, phone, status FROM users WHERE id = :uid
        """), {"uid": user["id"]})).first()
    await engine.dispose()

    dek_ct, phone_db, status = row
    assert dek_ct is None
    assert phone_db is None
    assert status == "disabled"


@pytest.mark.asyncio
async def test_delete_account_revokes_all_sessions(client):
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


@pytest.mark.asyncio
async def test_delete_account_allows_same_phone_reregister(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    await client.request(
        "DELETE",
        "/api/auth/account",
        cookies={"session": cookie},
        json={"confirm": "DELETE MY ACCOUNT"},
    )

    cookie2, user2 = await register_user(client, phone)
    assert cookie2 is not None
    assert cookie2 != cookie
