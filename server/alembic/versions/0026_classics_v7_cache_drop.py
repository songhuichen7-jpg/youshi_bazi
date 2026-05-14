"""Drop v7 classics cache rows after persona prompt softening.

Revision ID: 0026_classics_v7_cache_drop
Revises: 0025_classics_v6_cache_drop
Create Date: 2026-05-08
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0026_classics_v7_cache_drop"
down_revision: Union[str, Sequence[str], None] = "0025_classics_v6_cache_drop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM chart_cache WHERE kind = 'classics' AND key = 'v7'")


def downgrade() -> None:
    pass
