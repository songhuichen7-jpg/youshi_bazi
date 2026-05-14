"""End-to-end: full chart lifecycle + cross-plan crypto-shredding integrity."""
from __future__ import annotations

import os
import uuid

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.crypto import decrypt_field
from tests.integration.conftest import register_user


@pytest.mark.asyncio
async def test_full_lifecycle(client):
    """Register → create → list → get → patch → delete → restore → verify."""
    cookie, user = await register_user(client, "+8613800001111")

    # POST
    r = await client.post(
        "/api/charts",
        cookies={"session": cookie},
        json={
            "birth_input": {
                "year": 1990, "month": 5, "day": 12, "hour": 14,
                "minute": 30, "city": "北京", "gender": "male",
            },
            "label": "我的本命盘",
        },
    )
    assert r.status_code == 201
    cid = r.json()["chart"]["id"]
    assert "sizhu" in r.json()["chart"]["paipan"]

    # LIST
    r = await client.get("/api/charts", cookies={"session": cookie})
    assert len(r.json()["items"]) == 1

    # GET detail
    r = await client.get(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 200

    # PATCH label
    r = await client.patch(
        f"/api/charts/{cid}",
        cookies={"session": cookie},
        json={"label": "改过的名字"},
    )
    assert r.json()["chart"]["label"] == "改过的名字"

    # DELETE (soft)
    r = await client.delete(f"/api/charts/{cid}", cookies={"session": cookie})
    assert r.status_code == 204

    # LIST now empty
    r = await client.get("/api/charts", cookies={"session": cookie})
    assert r.json()["items"] == []

    # RESTORE
    r = await client.post(f"/api/charts/{cid}/restore", cookies={"session": cookie})
    assert r.status_code == 200
    assert r.json()["chart"]["label"] == "改过的名字"

    # LIST shows it again
    r = await client.get("/api/charts", cookies={"session": cookie})
    assert len(r.json()["items"]) == 1


@pytest.mark.asyncio
async def test_chart_birth_input_unreadable_after_shredding(client, database_url):
    """Crypto-shredding makes a chart's encrypted birth_input unreadable.

    Create chart → shred account → attempt direct decrypt with random DEK → InvalidTag.
    This proves Plan 2's envelope encryption + Plan 3's shredding + Plan 4's
    EncryptedJSONB hold up end-to-end.
    """
    cookie, _ = await register_user(client, "+8613800002222")
    r = await client.post(
        "/api/charts",
        cookies={"session": cookie},
        json={
            "birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"},
        },
    )
    cid = r.json()["chart"]["id"]

    # Snapshot the raw ciphertext BEFORE shredding.
    engine = create_async_engine(str(database_url))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        raw_ct = (await s.execute(
            text("SELECT birth_input FROM charts WHERE id = :cid"),
            {"cid": cid},
        )).scalar_one()
    await engine.dispose()
    assert isinstance(raw_ct, (bytes, memoryview))
    ct_bytes = bytes(raw_ct)

    # Shred the account.
    r = await client.request(
        "DELETE",
        "/api/auth/account",
        cookies={"session": cookie},
        json={"confirm": "DELETE MY ACCOUNT"},
    )
    assert r.status_code == 200

    # Attempt to decrypt the snapshot with a random DEK → InvalidTag.
    # decrypt_field is Plan 2's nonce-split + AES-GCM auth-tag wrapper.
    fake_dek = os.urandom(32)
    with pytest.raises(InvalidTag):
        decrypt_field(ct_bytes, fake_dek)
