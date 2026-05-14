"""EncryptedText — transparent per-user AES-256-GCM column encryption."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator


class EncryptedText(TypeDecorator):
    """Python ``str`` ↔ Postgres ``bytea`` (AES-GCM ciphertext).

    Requires an active ``user_dek_context()`` — outside one, ``process_*``
    raises RuntimeError. NULL values pass through unencrypted.
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect: Any) -> Optional[bytes]:
        if value is None:
            return None
        # Lazy import to dodge circular imports during model collection.
        from app.core.crypto import encrypt_field
        from app.db_types import get_current_dek

        dek = get_current_dek()
        if dek is None:
            raise RuntimeError(
                "no DEK in context — wrap this ORM op in user_dek_context()"
            )
        return encrypt_field(value.encode("utf-8"), dek)

    def process_result_value(self, value: Optional[bytes], dialect: Any) -> Optional[str]:
        if value is None:
            return None
        from app.core.crypto import decrypt_field
        from app.db_types import get_current_dek

        dek = get_current_dek()
        if dek is None:
            raise RuntimeError(
                "no DEK in context — wrap this ORM op in user_dek_context()"
            )
        return decrypt_field(value, dek).decode("utf-8")
