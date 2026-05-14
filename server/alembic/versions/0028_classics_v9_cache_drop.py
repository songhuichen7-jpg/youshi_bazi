"""Drop v9 classics cache rows after candidates 简体 + persona tier bump.

Revision ID: 0028_classics_v9_cache_drop
Revises: 0027_classics_v8_cache_drop
Create Date: 2026-05-08
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0028_classics_v9_cache_drop"
down_revision: Union[str, Sequence[str], None] = "0027_classics_v8_cache_drop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM chart_cache WHERE kind = 'classics' AND key = 'v9'")


def downgrade() -> None:
    pass
