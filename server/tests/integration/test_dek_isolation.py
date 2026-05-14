"""Two users' DEKs must be independent: user A's ciphertext must be opaque
to user B's DEK context."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from cryptography.exceptions import InvalidTag
from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_two_users_cannot_read_each_others_rows(database_url):
    from app.db_types import EncryptedText, user_dek_context

    engine = create_async_engine(database_url)
    meta = MetaData()
    t = Table(
        "t_isolation_test",
        meta,
        Column("id", String(8), primary_key=True),
        Column("val", EncryptedText, nullable=False),
    )
    async with engine.begin() as conn:
        await conn.run_sync(meta.drop_all)
        await conn.run_sync(meta.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    dek_alice = os.urandom(32)
    dek_bob = os.urandom(32)

    with user_dek_context(dek_alice):
        async with maker() as s:
            await s.execute(t.insert().values(id="alice", val="alice's secret"))
            await s.commit()
    with user_dek_context(dek_bob):
        async with maker() as s:
            await s.execute(t.insert().values(id="bob", val="bob's secret"))
            await s.commit()

    # Alice reading Alice's row → OK
    with user_dek_context(dek_alice):
        async with maker() as s:
            row = (await s.execute(t.select().where(t.c.id == "alice"))).first()
            assert row.val == "alice's secret"

    # Alice reading Bob's row → InvalidTag
    with user_dek_context(dek_alice):
        async with maker() as s:
            with pytest.raises(InvalidTag):
                row = (await s.execute(t.select().where(t.c.id == "bob"))).first()
                _ = row.val

    async with engine.begin() as conn:
        await conn.run_sync(meta.drop_all)
    await engine.dispose()
