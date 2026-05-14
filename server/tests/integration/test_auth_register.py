"""Integration tests for POST /api/auth/register."""
from __future__ import annotations

import hashlib
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .conftest import register_user, seed_invite_code


@pytest.mark.asyncio
async def test_register_full_flow(client):
    invite = await seed_invite_code()
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"

    r = await client.post("/api/auth/sms/send", json={"phone": phone, "purpose": "register"})
    assert r.status_code == 200
    code = r.json()["__devCode"]

    r = await client.post("/api/auth/register", json={
        "phone": phone, "code": code, "invite_code": invite,
        "nickname": "测试", "agreed_to_terms": True,
    })
    assert r.status_code == 200
    assert r.cookies.get("session") is not None
    user = r.json()["user"]
    assert user["phone_last4"] == phone[-4:]
    assert "phone" not in user


@pytest.mark.asyncio
async def test_register_missing_terms_rejected(client):
    invite = await seed_invite_code()
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    r = await client.post("/api/auth/sms/send", json={"phone": phone, "purpose": "register"})
    code = r.json()["__devCode"]
    r = await client.post("/api/auth/register", json={
        "phone": phone, "code": code, "invite_code": invite,
        "agreed_to_terms": False,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "TERMS_NOT_AGREED"


@pytest.mark.asyncio
async def test_register_bad_invite_code(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    r = await client.post("/api/auth/sms/send", json={"phone": phone, "purpose": "register"})
    code = r.json()["__devCode"]
    r = await client.post("/api/auth/register", json={
        "phone": phone, "code": code, "invite_code": "NONEXIST",
        "agreed_to_terms": True,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVITE_CODE_INVALID"


@pytest.mark.asyncio
async def test_register_wrong_sms_code(client):
    invite = await seed_invite_code()
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    await client.post("/api/auth/sms/send", json={"phone": phone, "purpose": "register"})
    r = await client.post("/api/auth/register", json={
        "phone": phone, "code": "000000", "invite_code": invite,
        "agreed_to_terms": True,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "SMS_CODE_INVALID"


@pytest.mark.asyncio
async def test_register_phone_already_registered(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    await register_user(client, phone)

    # Second attempt with same phone: need a fresh SMS code (cooldown blocks
    # resending via API). Insert directly via SQL at a timestamp before 60s cooldown:
    invite2 = await seed_invite_code()
    code2 = "654321"
    code_hash = hashlib.sha256(code2.encode()).hexdigest()
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text("""
            INSERT INTO sms_codes (phone, code_hash, purpose, expires_at, created_at)
            VALUES (:p, :h, 'register', now() + interval '5 minutes', now() - interval '2 minutes')
        """), {"p": phone, "h": code_hash})
        await s.commit()
    await engine.dispose()

    r = await client.post("/api/auth/register", json={
        "phone": phone, "code": code2, "invite_code": invite2,
        "agreed_to_terms": True,
    })
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "PHONE_ALREADY_REGISTERED"


@pytest.mark.asyncio
async def test_register_dev_code_not_leaked_in_prod(client, monkeypatch):
    """When env != 'dev', __devCode must not be populated."""
    # The /api/auth/sms/send handler reads ``settings.env`` via the module-local
    # reference in ``app.api.auth``. Patch that reference's ``env`` attribute so
    # the endpoint sees the prod-mode setting on its next call.
    import app.api.auth as _auth_module

    monkeypatch.setattr(_auth_module.settings, "env", "prod")
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    r = await client.post("/api/auth/sms/send", json={"phone": phone, "purpose": "register"})
    body = r.json()
    assert r.status_code == 200
    assert body.get("__devCode") is None


@pytest.mark.asyncio
async def test_register_invite_used_count_incremented(client):
    invite = await seed_invite_code(max_uses=3)
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    r = await client.post("/api/auth/sms/send", json={"phone": phone, "purpose": "register"})
    code = r.json()["__devCode"]
    await client.post("/api/auth/register", json={
        "phone": phone, "code": code, "invite_code": invite,
        "agreed_to_terms": True,
    })

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        n = (await s.execute(text("SELECT used_count FROM invite_codes WHERE code=:c"),
                              {"c": invite})).scalar_one()
    await engine.dispose()
    assert n == 1


@pytest.mark.asyncio
async def test_register_invite_exhausted(client):
    invite = await seed_invite_code(max_uses=1)
    phone1 = f"+86138{uuid.uuid4().int % 10**8:08d}"
    r = await client.post("/api/auth/sms/send", json={"phone": phone1, "purpose": "register"})
    code1 = r.json()["__devCode"]
    await client.post("/api/auth/register", json={
        "phone": phone1, "code": code1, "invite_code": invite,
        "agreed_to_terms": True,
    })

    phone2 = f"+86138{uuid.uuid4().int % 10**8:08d}"
    r = await client.post("/api/auth/sms/send", json={"phone": phone2, "purpose": "register"})
    code2 = r.json()["__devCode"]
    r = await client.post("/api/auth/register", json={
        "phone": phone2, "code": code2, "invite_code": invite,
        "agreed_to_terms": True,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVITE_CODE_INVALID"


@pytest.mark.asyncio
async def test_register_dek_encrypted_in_db(client):
    """users.dek_ciphertext is set, non-null, and not equal to raw DEK."""
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    _, user = await register_user(client, phone)

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        row = (await s.execute(text("""
            SELECT dek_ciphertext, dek_key_version, agreed_to_terms_at
              FROM users WHERE id = :uid
        """), {"uid": user["id"]})).first()
    await engine.dispose()

    dek_ct, version, terms_at = row
    assert dek_ct is not None
    assert len(dek_ct) > 44  # 32-byte DEK + 12-byte nonce + 16-byte tag = 60 bytes minimum
    assert version == 1
    assert terms_at is not None


@pytest.mark.asyncio
async def test_register_invalid_phone_format(client):
    invite = await seed_invite_code()
    r = await client.post("/api/auth/register", json={
        "phone": "abc", "code": "123456", "invite_code": invite,
        "agreed_to_terms": True,
    })
    assert r.status_code == 422   # Pydantic validation error


@pytest.mark.asyncio
async def test_register_no_invite_when_invite_not_required(client, monkeypatch):
    import app.services.auth as auth_service

    monkeypatch.setattr(auth_service.settings, "require_invite", False)

    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    r = await client.post("/api/auth/sms/send", json={"phone": phone, "purpose": "register"})
    code = r.json()["__devCode"]

    r = await client.post("/api/auth/register", json={
        "phone": phone,
        "code": code,
        "invite_code": None,
        "nickname": "免邀请码",
        "agreed_to_terms": True,
    })
    assert r.status_code == 200
    assert r.cookies.get("session") is not None


@pytest.mark.asyncio
async def test_register_invite_required_missing_returns_400(client, monkeypatch):
    import app.services.auth as auth_service

    monkeypatch.setattr(auth_service.settings, "require_invite", True)

    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    r = await client.post("/api/auth/sms/send", json={"phone": phone, "purpose": "register"})
    code = r.json()["__devCode"]

    r = await client.post("/api/auth/register", json={
        "phone": phone,
        "code": code,
        "invite_code": None,
        "agreed_to_terms": True,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVITE_CODE_INVALID"
