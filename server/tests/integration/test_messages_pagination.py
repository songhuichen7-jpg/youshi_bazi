"""Integration: keyset pagination over messages."""
from __future__ import annotations

import os
import uuid
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.integration.conftest import register_user


pytestmark = pytest.mark.asyncio


async def _register_with_chart(client):
    phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
    cookie, _ = await register_user(client, phone)
    r = await client.post("/api/charts", cookies={"session": cookie}, json={
        "birth_input": {"year": 1990, "month": 5, "day": 12, "hour": 12, "gender": "male"},
    })
    return cookie, r.json()["chart"]["id"], phone


async def _seed_messages_via_service(phone: str, conv_id: str, n: int):
    """Insert N user messages directly via the service (handles encrypted columns)."""
    from app.core.crypto import decrypt_dek
    from app.db_types import user_dek_context
    from app.services import message as msg_svc

    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        # Get user's DEK
        row = (await s.execute(
            text("SELECT dek_ciphertext FROM users WHERE phone=:p"),
            {"p": phone},
        )).first()
        kek = bytes.fromhex(os.environ["ENCRYPTION_KEK"])
        dek = decrypt_dek(row[0], kek)
        with user_dek_context(dek):
            import asyncio as _a
            for i in range(n):
                await msg_svc.insert(s, conversation_id=UUID(conv_id),
                                      role="user", content=f"m{i}")
                await s.commit()
                await _a.sleep(0.001)
    await engine.dispose()


async def test_pagination_three_pages_of_60(client):
    cookie, cid, phone = await _register_with_chart(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]
    await _seed_messages_via_service(phone, conv_id, 60)

    r1 = await client.get(
        f"/api/conversations/{conv_id}/messages?limit=25",
        cookies={"session": cookie},
    )
    assert r1.status_code == 200, r1.text
    page1 = r1.json()
    assert len(page1["items"]) == 25
    assert page1["items"][0]["content"] == "m59"
    assert page1["next_cursor"] is not None

    r2 = await client.get(
        f"/api/conversations/{conv_id}/messages?limit=25&before={page1['next_cursor']}",
        cookies={"session": cookie},
    )
    page2 = r2.json()
    assert len(page2["items"]) == 25
    assert page2["items"][0]["content"] == "m34"

    r3 = await client.get(
        f"/api/conversations/{conv_id}/messages?limit=25&before={page2['next_cursor']}",
        cookies={"session": cookie},
    )
    page3 = r3.json()
    assert len(page3["items"]) == 10
    assert page3["next_cursor"] is None


async def test_pagination_limit_validation(client):
    cookie, cid, _ = await _register_with_chart(client)
    r = await client.post(f"/api/charts/{cid}/conversations",
                           cookies={"session": cookie}, json={})
    conv_id = r.json()["id"]
    r1 = await client.get(f"/api/conversations/{conv_id}/messages?limit=0",
                            cookies={"session": cookie})
    assert r1.status_code == 422
    r2 = await client.get(f"/api/conversations/{conv_id}/messages?limit=101",
                            cookies={"session": cookie})
    assert r2.status_code == 422
