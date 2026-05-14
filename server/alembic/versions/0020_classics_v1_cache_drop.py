"""Drop legacy v1 classics cache rows.

Revision ID: 0020_classics_v1_cache_drop
Revises: 0019_users_onboarded_at
Create Date: 2026-05-08 00:00:00

The 古书定调 redesign uses cache key 'v2' (PersonaQuote + VerdictQuote
shape). Legacy 'v1' rows would sit unread forever — drop them to keep
chart_cache clean.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0020_classics_v1_cache_drop"
down_revision: Union[str, Sequence[str], None] = "0019_users_onboarded_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM chart_cache WHERE kind = 'classics' AND key = 'v1'"
    )


def downgrade() -> None:
    # 老 v1 数据已删除，无法回滚（v2 重新生成成本可控）
    pass
