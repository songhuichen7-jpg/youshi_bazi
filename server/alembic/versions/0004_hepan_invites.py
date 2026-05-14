"""hepan_invites table

Revision ID: 0004_hepan_invites
Revises: 0003_card_shares_and_events
Create Date: 2026-04-28 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_hepan_invites"
down_revision: Union[str, Sequence[str], None] = "0003_card_shares_and_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hepan_invites",
        sa.Column("slug", sa.String(length=12), nullable=False),
        # A side
        sa.Column("a_birth_hash", sa.String(length=64), nullable=False),
        sa.Column("a_type_id", sa.String(length=2), nullable=False),
        sa.Column("a_state", sa.String(length=4), nullable=False),
        sa.Column("a_day_stem", sa.String(length=2), nullable=False),
        sa.Column("a_nickname", sa.String(length=10), nullable=True),
        # B side (filled on complete)
        sa.Column("b_birth_hash", sa.String(length=64), nullable=True),
        sa.Column("b_type_id", sa.String(length=2), nullable=True),
        sa.Column("b_state", sa.String(length=4), nullable=True),
        sa.Column("b_day_stem", sa.String(length=2), nullable=True),
        sa.Column("b_nickname", sa.String(length=10), nullable=True),
        # Lifecycle
        sa.Column(
            "status",
            sa.String(length=12),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "share_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("slug", name="pk_hepan_invites"),
    )
    op.create_index(
        "ix_hepan_invites_a_birth_hash", "hepan_invites", ["a_birth_hash"]
    )
    op.create_index(
        "ix_hepan_invites_b_birth_hash", "hepan_invites", ["b_birth_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_hepan_invites_b_birth_hash", table_name="hepan_invites")
    op.drop_index("ix_hepan_invites_a_birth_hash", table_name="hepan_invites")
    op.drop_table("hepan_invites")
