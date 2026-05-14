from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import undefer

from app.core.crypto import decrypt_dek
from app.db_types import user_dek_context
from app.models.hepan_invite import HepanInvite
from app.models.user import User
from tests.integration.conftest import register_user


pytestmark = pytest.mark.asyncio


async def test_hepan_complete_stores_owner_encrypted_context_snapshots(client, database_url):
    phone = f"+86137{uuid.uuid4().int % 10**8:08d}"
    cookie, user = await register_user(client, phone)

    invite_resp = await client.post(
        "/api/hepan/invite",
        cookies={"session": cookie},
        json={
            "birth": {
                "year": 2003,
                "month": 8,
                "day": 29,
                "hour": 8,
                "minute": 25,
                "city": "长沙",
                "gender": "male",
                "useTrueSolarTime": True,
                "ziConvention": "early",
            },
            "nickname": "小夜灯",
        },
    )
    assert invite_resp.status_code == 200, invite_resp.text
    slug = invite_resp.json()["slug"]

    complete_resp = await client.post(
        f"/api/hepan/{slug}/complete",
        json={
            "birth": {
                "year": 2001,
                "month": 2,
                "day": 3,
                "hour": 9,
                "minute": 10,
                "city": "杭州",
                "gender": "female",
                "useTrueSolarTime": True,
                "ziConvention": "early",
            },
            "nickname": "多肉",
        },
    )
    assert complete_resp.status_code == 200, complete_resp.text

    engine = create_async_engine(database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            owner = await session.get(User, user["id"])
            dek = decrypt_dek(owner.dek_ciphertext, bytes.fromhex(os.environ["ENCRYPTION_KEK"]))
            with user_dek_context(dek):
                invite = (await session.execute(
                    select(HepanInvite)
                    .options(
                        undefer(HepanInvite.a_birth_input),
                        undefer(HepanInvite.a_paipan),
                        undefer(HepanInvite.b_birth_input),
                        undefer(HepanInvite.b_paipan),
                    )
                    .where(HepanInvite.slug == slug)
                )).scalar_one()

                assert invite.a_birth_input["city"] == "长沙"
                assert invite.a_birth_input["gender"] == "male"
                assert invite.a_paipan["birthInput"]["genderProvided"] is True
                assert invite.b_birth_input["city"] == "杭州"
                assert invite.b_birth_input["gender"] == "female"
                assert invite.b_paipan["birthInput"]["genderProvided"] is True
                assert invite.b_paipan["sizhu"]["day"]
    finally:
        await engine.dispose()
