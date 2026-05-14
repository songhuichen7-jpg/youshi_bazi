"""Hepan invite: encrypted birth and chart snapshots for main chat context.

Revision ID: 0017_hepan_context_snapshots
Revises: 0016_beta_analytics_admin
Create Date: 2026-05-07 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0017_hepan_context_snapshots"
down_revision: Union[str, Sequence[str], None] = "0016_beta_analytics_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hepan_invites", sa.Column("a_birth_input", sa.LargeBinary(), nullable=True))
    op.add_column("hepan_invites", sa.Column("a_paipan", sa.LargeBinary(), nullable=True))
    op.add_column("hepan_invites", sa.Column("b_birth_input", sa.LargeBinary(), nullable=True))
    op.add_column("hepan_invites", sa.Column("b_paipan", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("hepan_invites", "b_paipan")
    op.drop_column("hepan_invites", "b_birth_input")
    op.drop_column("hepan_invites", "a_paipan")
    op.drop_column("hepan_invites", "a_birth_input")
