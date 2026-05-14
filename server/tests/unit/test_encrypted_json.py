"""EncryptedJSONB — dict/list payloads, NULL passthrough, nested objects."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def ephemeral_json_table(database_url):
    from app.db_types.encrypted_json import EncryptedJSONB
    engine = create_async_engine(database_url)
    meta = MetaData()
    t = Table(
        "t_encrypted_json_test",
        meta,
        Column("id", String(8), primary_key=True),
        Column("val", EncryptedJSONB, nullable=True),
    )
    async with engine.begin() as conn:
        await conn.run_sync(meta.drop_all)
        await conn.run_sync(meta.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield t, maker
    async with engine.begin() as conn:
        await conn.run_sync(meta.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"k": "v"},
    {"nested": {"a": 1, "b": [1, 2, 3]}},
    [1, "two", {"three": 3}, None],
    {"chinese": "你好", "emoji": "🌸"},
    {},
    [],
])
async def test_json_roundtrip(ephemeral_json_table, payload):
    from app.db_types import user_dek_context
    t, maker = ephemeral_json_table
    dek = os.urandom(32)
    with user_dek_context(dek):
        async with maker() as s:
            await s.execute(t.insert().values(id="x", val=payload))
            await s.commit()
            row = (await s.execute(t.select())).first()
            assert row.val == payload


@pytest.mark.asyncio
async def test_json_null_passthrough(ephemeral_json_table):
    from app.db_types import user_dek_context
    t, maker = ephemeral_json_table
    dek = os.urandom(32)
    with user_dek_context(dek):
        async with maker() as s:
            await s.execute(t.insert().values(id="n", val=None))
            await s.commit()
            row = (await s.execute(t.select().where(t.c.id == "n"))).first()
            assert row.val is None


@pytest.mark.asyncio
async def test_json_missing_dek_context_raises(ephemeral_json_table):
    from sqlalchemy.exc import StatementError
    t, maker = ephemeral_json_table
    async with maker() as s:
        with pytest.raises(StatementError, match="no DEK in context") as exc_info:
            await s.execute(t.insert().values(id="z", val={"k": 1}))
            await s.commit()
    assert isinstance(exc_info.value.orig, RuntimeError)
