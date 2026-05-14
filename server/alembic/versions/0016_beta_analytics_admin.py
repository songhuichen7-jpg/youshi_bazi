"""Beta analytics: event taxonomy + UUID user attribution.

Revision ID: 0016_beta_analytics_admin
Revises: 0015_internal_beta_default_pro
Create Date: 2026-05-05 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_beta_analytics_admin"
down_revision: Union[str, Sequence[str], None] = "0015_internal_beta_default_pro"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "events",
        "event",
        existing_type=sa.String(length=30),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "events",
        "user_id",
        existing_type=sa.BigInteger(),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=True,
        postgresql_using="NULL::uuid",
    )
    op.create_index("ix_events_user_id", "events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_events_user_id", table_name="events")
    op.alter_column(
        "events",
        "user_id",
        existing_type=postgresql.UUID(as_uuid=True),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="NULL::bigint",
    )
    op.alter_column(
        "events",
        "event",
        existing_type=sa.String(length=50),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
