"""Drop classics cache rows whose payload is all-null.

Revision ID: 0030_classics_drop_null
Revises: 0029_classics_v10_cache_drop
Create Date: 2026-05-08

After v11 we stopped caching null payloads, but rows already in the table
under v11 can still be all-null. Decrypt the content column is hard from
SQL, but we can match the encrypted form: model_dump_json(exclude_none=
True) on a {persona: None, verdict: None} ChartClassicsResponse renders
as exactly '{}'. The encrypted column will hash to a deterministic
ciphertext for that exact 2-byte plaintext (per current EncryptedText
impl). However, the IV randomization means we can't filter by ciphertext.
Simplest: blow away all v11 rows — users that had real content will
re-fetch (one extra LLM run) but the empty-stuck users get unblocked.
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0030_classics_drop_null"
down_revision: Union[str, Sequence[str], None] = "0029_classics_v10_cache_drop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM chart_cache WHERE kind = 'classics' AND key = 'v11'")


def downgrade() -> None:
    pass
