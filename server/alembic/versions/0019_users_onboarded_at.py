"""Track when user has resolved the onboarding modal (completed or dismissed).

Revision ID: 0019_users_onboarded_at
Revises: 0018_conversations_hepan_slug
Create Date: 2026-05-07 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0019_users_onboarded_at"
down_revision: Union[str, Sequence[str], None] = "0018_conversations_hepan_slug"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "onboarded_at")
