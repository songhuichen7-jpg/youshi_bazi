"""Crypto-shredding: dropping a DEK makes prior ciphertext permanently
unreadable — even the attacker with KEK and DB backup can't recover."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from cryptography.exceptions import InvalidTag
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.mark.asyncio
async def test_shredding_makes_ciphertext_unreadable(database_url):
    """Scenario:
      1. User has DEK A; encrypt chart
      2. User requests account deletion → DEK A is destroyed
      3. Attacker holds KEK + DB backup; generates DEK B (random)
      4. Attacker cannot decrypt — DEK B ≠ DEK A, AESGCM fails.
    """
    from app.core.crypto import decrypt_field, encrypt_field, generate_dek

    dek_a = generate_dek()
    ciphertext = encrypt_field(b"my private birth data", dek_a)

    # Shredding: pretend we overwrote DEK A. Attacker guesses.
    dek_b = generate_dek()
    with pytest.raises(InvalidTag):
        decrypt_field(ciphertext, dek_b)

    # Proof of positive control: with the original DEK, it still decrypts
    # (i.e. ciphertext is otherwise intact — the key is the only missing piece).
    assert decrypt_field(ciphertext, dek_a) == b"my private birth data"


@pytest.mark.asyncio
async def test_shredding_end_to_end_with_db(database_url):
    """Integration: write via ORM, drop the DEK, confirm neither new DEK nor
    the original column value can reveal the plaintext."""
    from sqlalchemy import text
    from app.db_types import EncryptedText, user_dek_context
    from sqlalchemy import Column, MetaData, String, Table

    engine = create_async_engine(database_url)
    meta = MetaData()
    t = Table(
        "t_shred_test",
        meta,
        Column("id", String(8), primary_key=True),
        Column("val", EncryptedText, nullable=False),
    )
    async with engine.begin() as conn:
        await conn.run_sync(meta.drop_all)
        await conn.run_sync(meta.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    dek_a = os.urandom(32)
    # Step 1: write with DEK A
    with user_dek_context(dek_a):
        async with maker() as s:
            await s.execute(t.insert().values(id="1", val="secret"))
            await s.commit()

    # Step 2: raw read — confirm ciphertext is in DB
    async with maker() as s:
        raw = (await s.execute(text("SELECT val FROM t_shred_test WHERE id='1'"))).scalar_one()
    assert raw != b"secret"

    # Step 3: "shred" DEK A (simulated: just forget it). Try DEK B.
    dek_b = os.urandom(32)
    with user_dek_context(dek_b):
        async with maker() as s:
            with pytest.raises(InvalidTag):
                row = (await s.execute(t.select())).first()
                _ = row.val

    # Step 4: DEK A still decrypts (positive control)
    with user_dek_context(dek_a):
        async with maker() as s:
            row = (await s.execute(t.select())).first()
            assert row.val == "secret"

    async with engine.begin() as conn:
        await conn.run_sync(meta.drop_all)
    await engine.dispose()
