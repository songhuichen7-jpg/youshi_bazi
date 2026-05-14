"""Shared fixtures + helpers for auth integration tests."""
from __future__ import annotations

import importlib
import os
import sys
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def client(database_url, monkeypatch):
    """FastAPI TestClient bound to the real testcontainer DB.

    Bridges the module-level engine singleton in app.core.db to the
    testcontainers URL by reloading config + main after env munging.
    """
    monkeypatch.setenv("DATABASE_URL", str(database_url))
    monkeypatch.setenv("ENV", "dev")  # enables __devCode echo

    cfg_mod = sys.modules.get("app.core.config")
    if cfg_mod is not None:
        importlib.reload(cfg_mod)

    from app.core import db as db_mod
    await db_mod.dispose_engine()

    main_mod = sys.modules.get("app.main")
    if main_mod is not None:
        importlib.reload(main_mod)
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        async with app.router.lifespan_context(app):
            yield c

    await db_mod.dispose_engine()


async def seed_invite_code(max_uses: int = 10) -> str:
    """Insert bootstrap user + invite code; returns the invite code string."""
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        bootstrap_phone = f"+86138{uuid.uuid4().int % 10**8:08d}"
        await s.execute(
            text(
                """
                INSERT INTO users (phone, phone_last4, dek_ciphertext, dek_key_version)
                VALUES (:phone, :last4, :ct, 1)
                """
            ),
            {
                "phone": bootstrap_phone,
                "last4": bootstrap_phone[-4:],
                "ct": b"\x00" * 44,
            },
        )
        bootstrap_id = (
            await s.execute(
                text("SELECT id FROM users WHERE phone=:p"),
                {"p": bootstrap_phone},
            )
        ).scalar_one()
        invite = f"INV-{uuid.uuid4().hex[:8].upper()}"
        await s.execute(
            text(
                """
                INSERT INTO invite_codes (code, created_by, max_uses)
                VALUES (:c, :u, :mu)
                """
            ),
            {"c": invite, "u": bootstrap_id, "mu": max_uses},
        )
        await s.commit()
    await engine.dispose()
    return invite


async def upgrade_user_plan(user_id: str, plan: str = "pro") -> None:
    """直接把用户 plan 升到指定档位 — 给"测命盘上限边界"这类要造 5+ 张
    chart 的测试用。lite 默认 cap=2，跑不到正经的 cap-overflow 边界。

    plan 取值参见 app/core/quotas.py CHART_MAX_BY_PLAN：
      lite=2 / standard=5 / pro=20。
    """
    engine = create_async_engine(os.environ["DATABASE_URL"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(
            text("UPDATE users SET plan = :p WHERE id = :u"),
            {"p": plan, "u": user_id},
        )
        await s.commit()
    await engine.dispose()


async def register_user(
    client: AsyncClient,
    phone: str,
    invite: str | None = None,
) -> tuple[str, dict]:
    """Full register flow. Returns (session_cookie, user_dict)."""
    if invite is None:
        invite = await seed_invite_code()

    r = await client.post(
        "/api/auth/sms/send",
        json={"phone": phone, "purpose": "register"},
    )
    assert r.status_code == 200, r.text
    code = r.json()["__devCode"]

    r = await client.post(
        "/api/auth/register",
        json={
            "phone": phone,
            "code": code,
            "invite_code": invite,
            "nickname": "test",
            "agreed_to_terms": True,
        },
    )
    assert r.status_code == 200, r.text
    return r.cookies.get("session"), r.json()["user"]
