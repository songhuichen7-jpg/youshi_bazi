"""Unit tests for app.core.crypto — pure-function crypto primitives."""
from __future__ import annotations

import os

import pytest
from cryptography.exceptions import InvalidTag


# ---------- load_kek ---------------------------------------------------
def test_load_kek_reads_64_hex(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEK", "aa" * 32)
    import importlib
    import app.core.config as cfg
    importlib.reload(cfg)
    from app.core.crypto import load_kek
    kek = load_kek()
    assert isinstance(kek, bytes) and len(kek) == 32


def test_load_kek_rejects_sentinel(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEK", "__CHANGE_ME_64_HEX__")
    import importlib
    import app.core.config as cfg
    importlib.reload(cfg)
    from app.core.crypto import load_kek
    with pytest.raises(RuntimeError, match="sentinel"):
        load_kek()


def test_load_kek_rejects_invalid_hex(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEK", "zzz")
    import importlib
    import app.core.config as cfg
    importlib.reload(cfg)
    from app.core.crypto import load_kek
    with pytest.raises(ValueError):
        load_kek()


# ---------- generate_dek + encrypt_dek / decrypt_dek -------------------
def test_dek_roundtrip():
    from app.core.crypto import decrypt_dek, encrypt_dek, generate_dek
    kek = os.urandom(32)
    dek = generate_dek()
    assert len(dek) == 32
    ct = encrypt_dek(dek, kek)
    assert ct != dek
    recovered = decrypt_dek(ct, kek)
    assert recovered == dek


def test_decrypt_dek_rejects_tampered():
    from app.core.crypto import decrypt_dek, encrypt_dek, generate_dek
    kek = os.urandom(32)
    dek = generate_dek()
    ct = bytearray(encrypt_dek(dek, kek))
    ct[-1] ^= 0x01
    with pytest.raises(InvalidTag):
        decrypt_dek(bytes(ct), kek)


# ---------- encrypt_field / decrypt_field ------------------------------
@pytest.mark.parametrize("payload", [
    b"",
    b"a",
    b"Hello, world",
    "你好世界".encode("utf-8"),
    "🎉🌈".encode("utf-8"),
    b"x" * (1024 * 1024),  # 1 MiB
])
def test_field_roundtrip(payload):
    from app.core.crypto import decrypt_field, encrypt_field
    dek = os.urandom(32)
    ct = encrypt_field(payload, dek)
    assert ct != payload
    assert decrypt_field(ct, dek) == payload


def test_field_nonce_is_unique():
    """Same plaintext encrypted 1000 times should yield 1000 distinct nonces."""
    from app.core.crypto import encrypt_field
    dek = os.urandom(32)
    nonces = set()
    for _ in range(1000):
        ct = encrypt_field(b"same", dek)
        nonces.add(ct[:12])  # first 12 bytes = nonce
    assert len(nonces) == 1000


def test_field_tamper_ciphertext_raises():
    from app.core.crypto import decrypt_field, encrypt_field
    dek = os.urandom(32)
    ct = bytearray(encrypt_field(b"secret", dek))
    ct[-1] ^= 0x01
    with pytest.raises(InvalidTag):
        decrypt_field(bytes(ct), dek)


def test_field_tamper_nonce_raises():
    from app.core.crypto import decrypt_field, encrypt_field
    dek = os.urandom(32)
    ct = bytearray(encrypt_field(b"secret", dek))
    ct[0] ^= 0x01  # first byte is nonce
    with pytest.raises(InvalidTag):
        decrypt_field(bytes(ct), dek)


def test_field_wrong_key_raises():
    from app.core.crypto import decrypt_field, encrypt_field
    dek_a = os.urandom(32)
    dek_b = os.urandom(32)
    ct = encrypt_field(b"secret", dek_a)
    with pytest.raises(InvalidTag):
        decrypt_field(ct, dek_b)
