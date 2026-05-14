"""Drop v5 classics cache rows.

Revision ID: 0024_classics_v5_cache_drop
Revises: 0023_classics_v4_cache_drop
Create Date: 2026-05-08
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0024_classics_v5_cache_drop"
down_revision: Union[str, Sequence[str], None] = "0023_classics_v4_cache_drop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM chart_cache WHERE kind = 'classics' AND key = 'v5'")


def downgrade() -> None:
    pass
