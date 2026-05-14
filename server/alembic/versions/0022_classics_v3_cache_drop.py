"""Drop v3 classics cache rows after persona+verdict prompt loosening.

Revision ID: 0022_classics_v3_cache_drop
Revises: 0021_classics_v2_cache_drop
Create Date: 2026-05-08
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "0022_classics_v3_cache_drop"
down_revision: Union[str, Sequence[str], None] = "0021_classics_v2_cache_drop"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("DELETE FROM chart_cache WHERE kind = 'classics' AND key = 'v3'")

def downgrade() -> None:
    pass
