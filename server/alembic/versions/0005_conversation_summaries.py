"""conversation_summaries table

Revision ID: 0005_conversation_summaries
Revises: 0004_hepan_invites
Create Date: 2026-04-29 00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_conversation_summaries"
down_revision: Union[str, Sequence[str], None] = "0004_hepan_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_summaries",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("summary", sa.LargeBinary(), nullable=False),
        sa.Column("covered_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "covered_message_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_conversation_summaries_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["covered_message_id"],
            ["messages.id"],
            name="fk_conversation_summaries_covered_message_id_messages",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("conversation_id", name="pk_conversation_summaries"),
    )


def downgrade() -> None:
    op.drop_table("conversation_summaries")
