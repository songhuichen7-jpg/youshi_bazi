"""EncryptedJSONB — transparent per-user AES-256-GCM encryption of JSON payloads.

Serialization: ``json.dumps(value, ensure_ascii=False).encode("utf-8")`` →
AES-GCM → bytea. Inverse on read.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator


class EncryptedJSONB(TypeDecorator):
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Optional[Any], dialect: Any) -> Optional[bytes]:
        if value is None:
            return None
        from app.core.crypto import encrypt_field
        from app.db_types import get_current_dek

        dek = get_current_dek()
        if dek is None:
            raise RuntimeError(
                "no DEK in context — wrap this ORM op in user_dek_context()"
            )
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        return encrypt_field(payload, dek)

    def process_result_value(self, value: Optional[bytes], dialect: Any) -> Optional[Any]:
        if value is None:
            return None
        from app.core.crypto import decrypt_field
        from app.db_types import get_current_dek

        dek = get_current_dek()
        if dek is None:
            raise RuntimeError(
                "no DEK in context — wrap this ORM op in user_dek_context()"
            )
        return json.loads(decrypt_field(value, dek).decode("utf-8"))
