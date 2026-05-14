"""EncryptedText TypeDecorator — contextvars DEK + transparent crypto."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def ephemeral_table(database_url):
    """A tiny throwaway table using EncryptedText, created per-test."""
    from app.db_types.encrypted_text import EncryptedText
    engine = create_async_engine(database_url)
    meta = MetaData()
    t = Table(
        "t_encrypted_text_test",
        meta,
        Column("id", String(8), primary_key=True),
        Column("val", EncryptedText, nullable=True),
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
async def test_roundtrip_under_dek_context(ephemeral_table):
    from app.db_types import user_dek_context
    t, maker = ephemeral_table
    dek = os.urandom(32)

    with user_dek_context(dek):
        async with maker() as s:
            await s.execute(t.insert().values(id="a", val="hello 你好"))
            await s.commit()
            row = (await s.execute(t.select())).first()
            assert row.val == "hello 你好"


@pytest.mark.asyncio
async def test_stored_bytes_differ_from_plaintext(ephemeral_table):
    """Read raw bytea via a separate connection without DEK context."""
    from sqlalchemy import text
    from app.db_types import user_dek_context
    t, maker = ephemeral_table
    dek = os.urandom(32)

    with user_dek_context(dek):
        async with maker() as s:
            await s.execute(t.insert().values(id="b", val="plaintext"))
            await s.commit()

    # Raw read — no DEK context, use a plain SELECT for bytes column.
    async with maker() as s:
        raw = await s.execute(text("SELECT val FROM t_encrypted_text_test WHERE id = 'b'"))
        stored = raw.scalar_one()
        assert stored != b"plaintext"
        assert len(stored) > len(b"plaintext")  # nonce + tag overhead


@pytest.mark.asyncio
async def test_missing_dek_context_raises(ephemeral_table):
    from sqlalchemy.exc import StatementError

    t, maker = ephemeral_table
    async with maker() as s:
        # SQLAlchemy wraps the RuntimeError from process_bind_param in a
        # StatementError (which exposes the original via .orig / message).
        with pytest.raises(StatementError, match="no DEK in context") as exc_info:
            await s.execute(t.insert().values(id="c", val="x"))
            await s.commit()
        assert isinstance(exc_info.value.orig, RuntimeError)


@pytest.mark.asyncio
async def test_cross_dek_read_raises(ephemeral_table):
    from cryptography.exceptions import InvalidTag
    from app.db_types import user_dek_context
    t, maker = ephemeral_table
    dek_a = os.urandom(32)
    dek_b = os.urandom(32)

    with user_dek_context(dek_a):
        async with maker() as s:
            await s.execute(t.insert().values(id="d", val="cross"))
            await s.commit()

    with user_dek_context(dek_b):
        async with maker() as s:
            with pytest.raises(InvalidTag):
                row = (await s.execute(t.select().where(t.c.id == "d"))).first()
                _ = row.val


@pytest.mark.asyncio
async def test_null_value_roundtrip(ephemeral_table):
    from app.db_types import user_dek_context
    t, maker = ephemeral_table
    dek = os.urandom(32)

    with user_dek_context(dek):
        async with maker() as s:
            await s.execute(t.insert().values(id="e", val=None))
            await s.commit()
            row = (await s.execute(t.select().where(t.c.id == "e"))).first()
            assert row.val is None
