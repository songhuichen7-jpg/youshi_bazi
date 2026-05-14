"""Envelope encryption primitives.

Layers:
    KEK (32 bytes, process-global)
      ↓ AES-256-GCM
    DEK (32 bytes, per user)
      ↓ AES-256-GCM
    field ciphertext (nonce || tagged_ct)

Ciphertext format: ``nonce (12B) || aesgcm_ciphertext_with_tag``.
"""
from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# NOTE: AES-GCM standard nonce size.
NONCE_SIZE = 12
KEY_SIZE = 32
_SENTINEL = "__CHANGE_ME_64_HEX__"


def load_kek() -> bytes:
    """Read settings.encryption_kek (64 hex) → 32 bytes. Fails loudly.

    Import ``settings`` lazily so tests that reload ``app.core.config`` (via
    ``importlib.reload`` or ``sys.modules.pop``) always see the freshest
    singleton — never a stale reference captured at import time.
    """
    from app.core.config import settings
    raw = settings.encryption_kek
    if raw == _SENTINEL:
        raise RuntimeError(
            "sentinel ENCRYPTION_KEK detected — generate a real key: "
            "python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    kek = bytes.fromhex(raw)  # raises ValueError if not hex
    if len(kek) != KEY_SIZE:
        raise ValueError(f"KEK must be {KEY_SIZE} bytes, got {len(kek)}")
    return kek


def generate_dek() -> bytes:
    """Generate a fresh 32-byte DEK."""
    return os.urandom(KEY_SIZE)


def _encrypt(plaintext: bytes, key: bytes) -> bytes:
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_SIZE)
    ct = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ct


def _decrypt(ciphertext: bytes, key: bytes) -> bytes:
    if len(ciphertext) < NONCE_SIZE:
        # InvalidTag would be raised below anyway, but short-circuit.
        from cryptography.exceptions import InvalidTag
        raise InvalidTag("ciphertext shorter than nonce size")
    nonce, ct = ciphertext[:NONCE_SIZE], ciphertext[NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, associated_data=None)


def encrypt_dek(dek: bytes, kek: bytes) -> bytes:
    """Wrap a user DEK with the process KEK."""
    return _encrypt(dek, kek)


def decrypt_dek(ciphertext: bytes, kek: bytes) -> bytes:
    """Unwrap a user DEK. Raises InvalidTag if tampered."""
    return _decrypt(ciphertext, kek)


def encrypt_field(plaintext: bytes, dek: bytes) -> bytes:
    """Encrypt a single field's bytes with the user DEK."""
    return _encrypt(plaintext, dek)


def decrypt_field(ciphertext: bytes, dek: bytes) -> bytes:
    """Decrypt a field. Raises InvalidTag on tamper / wrong key."""
    return _decrypt(ciphertext, dek)
