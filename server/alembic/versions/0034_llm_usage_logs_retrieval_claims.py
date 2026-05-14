"""Add retrieval_claims column to llm_usage_logs.

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0034_llm_retrieval_claims"
down_revision = "0033_agent_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_usage_logs",
        sa.Column("retrieval_claims", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_usage_logs", "retrieval_claims")
