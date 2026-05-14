"""Drop v8 classics cache rows after persona prompt simplification.

Revision ID: 0027_classics_v8_cache_drop
Revises: 0026_classics_v7_cache_drop
Create Date: 2026-05-08
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0027_classics_v8_cache_drop"
down_revision: Union[str, Sequence[str], None] = "0026_classics_v7_cache_drop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM chart_cache WHERE kind = 'classics' AND key = 'v8'")


def downgrade() -> None:
    pass
