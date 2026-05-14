"""Encrypted SQLAlchemy column types + request-scoped DEK context."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

_current_dek: ContextVar[Optional[bytes]] = ContextVar("user_dek", default=None)


def get_current_dek() -> Optional[bytes]:
    """Return the DEK for the current async task / request, or None."""
    return _current_dek.get()


@contextmanager
def user_dek_context(dek: bytes) -> Iterator[bytes]:
    """Bind a DEK for the duration of the ``with`` block.

    ORM code inside the block transparently encrypts/decrypts
    EncryptedText / EncryptedJSONB columns with this DEK. Reset on exit.
    """
    token = _current_dek.set(dek)
    try:
        yield dek
    finally:
        _current_dek.reset(token)


# Re-export the type classes (imported lazily by alembic / models).
from app.db_types.encrypted_text import EncryptedText  # noqa: E402
from app.db_types.encrypted_json import EncryptedJSONB  # noqa: E402

__all__ = ["EncryptedText", "EncryptedJSONB", "user_dek_context", "get_current_dek"]
