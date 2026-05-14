"""card_shares and events

Revision ID: 0003_card_shares_and_events
Revises: 0002_user_fields_for_auth
Create Date: 2026-04-24 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_card_shares_and_events"
down_revision: Union[str, Sequence[str], None] = "0002_user_fields_for_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_shares",
        sa.Column("slug", sa.String(length=12), nullable=False),
        sa.Column("birth_hash", sa.String(length=64), nullable=False),
        sa.Column("type_id", sa.String(length=2), nullable=False),
        sa.Column("cosmic_name", sa.String(length=20), nullable=False),
        sa.Column("suffix", sa.String(length=30), nullable=False),
        sa.Column("nickname", sa.String(length=10), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "share_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint("slug", name="pk_card_shares"),
    )
    op.create_index("ix_card_shares_birth_hash", "card_shares", ["birth_hash"])

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event", sa.String(length=30), nullable=False),
        sa.Column("type_id", sa.String(length=2), nullable=True),
        sa.Column("channel", sa.String(length=30), nullable=True),
        sa.Column("from_param", sa.String(length=30), nullable=True),
        sa.Column("share_slug", sa.String(length=12), nullable=True),
        sa.Column("anonymous_id", sa.String(length=40), nullable=True),
        sa.Column("session_id", sa.String(length=40), nullable=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("viewport", sa.String(length=20), nullable=True),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
    )
    op.create_index("ix_events_event", "events", ["event"])
    op.create_index("ix_events_share_slug", "events", ["share_slug"])
    op.create_index("ix_events_anonymous_id", "events", ["anonymous_id"])
    op.create_index("ix_events_created_at", "events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_events_created_at", table_name="events")
    op.drop_index("ix_events_anonymous_id", table_name="events")
    op.drop_index("ix_events_share_slug", table_name="events")
    op.drop_index("ix_events_event", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_card_shares_birth_hash", table_name="card_shares")
    op.drop_table("card_shares")
