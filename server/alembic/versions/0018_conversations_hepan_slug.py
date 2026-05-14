"""Bind a conversation to an optional hepan invite.

Revision ID: 0018_conversations_hepan_slug
Revises: 0017_hepan_context_snapshots
Create Date: 2026-05-07 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0018_conversations_hepan_slug"
down_revision: Union[str, Sequence[str], None] = "0017_hepan_context_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("hepan_slug", sa.String(length=12), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_hepan_slug_hepan_invites",
        source_table="conversations",
        referent_table="hepan_invites",
        local_cols=["hepan_slug"],
        remote_cols=["slug"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_conversations_chart_hepan",
        "conversations",
        ["chart_id", "hepan_slug"],
    )


def downgrade() -> None:
    op.drop_index("idx_conversations_chart_hepan", table_name="conversations")
    op.drop_constraint("fk_conversations_hepan_slug_hepan_invites", "conversations", type_="foreignkey")
    op.drop_column("conversations", "hepan_slug")
