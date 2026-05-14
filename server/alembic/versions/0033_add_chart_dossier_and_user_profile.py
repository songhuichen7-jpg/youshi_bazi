"""Add chart_dossier and user_profile tables for agent memory."""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0033_agent_memory"
down_revision: Union[str, Sequence[str], None] = "0032_section_cache_drop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chart_dossier",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("chart_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("finding", sa.Text(), nullable=False),
        sa.Column("source_message_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_chart_dossier"),
        sa.ForeignKeyConstraint(["chart_id"], ["charts.id"],
                                name="fk_chart_dossier_chart_id_charts",
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_message_id"], ["messages.id"],
                                name="fk_chart_dossier_source_message_id_messages",
                                ondelete="SET NULL"),
        sa.UniqueConstraint("chart_id", "key", name="uq_chart_dossier_chart_key"),
    )
    op.create_index("ix_chart_dossier_chart_id", "chart_dossier", ["chart_id"])

    op.create_table(
        "user_profile",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_user_profile"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_user_profile_user_id_users",
                                ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "key", name="uq_user_profile_user_key"),
    )
    op.create_index("ix_user_profile_user_id", "user_profile", ["user_id"])


def downgrade() -> None:
    op.drop_table("user_profile")
    op.drop_table("chart_dossier")
