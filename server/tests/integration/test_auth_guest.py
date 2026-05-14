"""Integration tests for POST /api/auth/guest."""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.nickname_pool import NICKNAMES


@pytest.mark.asyncio
async def test_guest_login_creates_dev_session_and_user(client):
    r = await client.post("/api/auth/guest")
    assert r.status_code == 200
    assert r.cookies.get("session") is not None

    body = r.json()
    # Plan: onboarding-and-identity-sync — guest 创建时 nickname 是池里
    # 随机抽的二字文学名，不再是硬编码 '游客'。
    assert body["user"]["nickname"] in NICKNAMES
    assert body["user"]["phone_last4"]

    me = await client.get("/api/auth/me", cookies={"session": r.cookies.get("session")})
    assert me.status_code == 200
    assert me.json()["user"]["id"] == body["user"]["id"]


@pytest.mark.asyncio
async def test_guest_login_replaces_stale_guest_token_with_bad_dek(client):
    import os

    r = await client.post("/api/auth/guest")
    assert r.status_code == 200
    stale_user_id = r.json()["user"]["id"]
    stale_token = r.json()["guest_token"]

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(
            text("UPDATE users SET dek_ciphertext = :ct WHERE id = :uid"),
            {"ct": b"\x00" * 44, "uid": stale_user_id},
        )
        await s.commit()
    await engine.dispose()

    restored = await client.post("/api/auth/guest", json={"guest_token": stale_token})
    assert restored.status_code == 200, restored.text
    assert restored.json()["user"]["id"] != stale_user_id
    assert restored.json()["guest_token"] != stale_token

    me = await client.get(
        "/api/auth/me",
        cookies={"session": restored.cookies.get("session")},
    )
    assert me.status_code == 200
    assert me.json()["user"]["id"] == restored.json()["user"]["id"]


@pytest.mark.asyncio
async def test_guest_login_hidden_in_prod_without_beta_flag(client, monkeypatch):
    import app.api.auth as auth_api

    monkeypatch.setattr(auth_api.settings, "env", "prod")
    monkeypatch.setattr(auth_api.settings, "guest_login_enabled", False)

    r = await client.post("/api/auth/guest")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_guest_login_enabled_for_internal_beta_prod(client, monkeypatch):
    import app.api.auth as auth_api

    monkeypatch.setattr(auth_api.settings, "env", "prod")
    monkeypatch.setattr(auth_api.settings, "guest_login_enabled", True)

    r = await client.post("/api/auth/guest")
    assert r.status_code == 200
    assert r.json()["user"]["nickname"] in NICKNAMES
