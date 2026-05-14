"""hepan_context_for_user — conv_hepan_slug beats client_context."""
from __future__ import annotations

import os
import uuid
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.crypto import decrypt_dek
from app.db_types import user_dek_context
from app.models.user import User
from app.services.hepan.context import hepan_context_for_user
from tests.integration.conftest import register_user


pytestmark = pytest.mark.asyncio


async def _setup_user_with_completed_hepan(client) -> tuple[UUID, str]:
    """Register a user and run the A-invites + B-completes flow.

    Returns ``(user_id, slug)`` for use in context-precedence assertions.
    """
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
    return UUID(user["id"]), slug


async def test_conv_slug_takes_precedence_over_client_context(client, database_url):
    """When both are set, conv_hepan_slug wins — even if client_context.slug is bogus."""
    user_id, slug = await _setup_user_with_completed_hepan(client)

    engine = create_async_engine(database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            owner = await session.get(User, user_id)
            dek = decrypt_dek(owner.dek_ciphertext, bytes.fromhex(os.environ["ENCRYPTION_KEK"]))
            with user_dek_context(dek):
                summary = await hepan_context_for_user(
                    session, user_id,
                    client_context={"hepan": {"slug": "OTHER_SLUG_THAT_DOESNT_EXIST"}},
                    conv_hepan_slug=slug,
                )
        assert "【当前合盘上下文】" in summary
    finally:
        await engine.dispose()


async def test_client_context_used_when_conv_slug_missing(client, database_url):
    """Legacy fallback: conv_slug=None → client_context.hepan.slug is used."""
    user_id, slug = await _setup_user_with_completed_hepan(client)

    engine = create_async_engine(database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            owner = await session.get(User, user_id)
            dek = decrypt_dek(owner.dek_ciphertext, bytes.fromhex(os.environ["ENCRYPTION_KEK"]))
            with user_dek_context(dek):
                summary = await hepan_context_for_user(
                    session, user_id,
                    client_context={"hepan": {"slug": slug}},
                    conv_hepan_slug=None,
                )
        assert "【当前合盘上下文】" in summary
    finally:
        await engine.dispose()
