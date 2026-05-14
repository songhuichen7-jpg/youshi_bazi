"""Drop v2 classics cache rows after persona_match fix.

Revision ID: 0021_classics_v2_cache_drop
Revises: 0020_classics_v1_cache_drop
Create Date: 2026-05-08 00:00:00

The persona_match general-tier regex was too strict and dropped most
real-world hits, leaving cached responses with persona=null. Bumping
cache version v2 → v3 + dropping v2 rows forces regeneration.
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0021_classics_v2_cache_drop"
down_revision: Union[str, Sequence[str], None] = "0020_classics_v1_cache_drop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM chart_cache WHERE kind = 'classics' AND key = 'v2'"
    )


def downgrade() -> None:
    pass
