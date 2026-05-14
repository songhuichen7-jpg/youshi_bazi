"""user_fields_for_auth: allow dek_ciphertext NULL + add agreed_to_terms_at

Revision ID: 0002_user_fields_for_auth
Revises: 0001_baseline
Create Date: 2026-04-17 14:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_user_fields_for_auth"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("agreed_to_terms_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("users", "dek_ciphertext", nullable=True)
    # Crypto-shredding (spec §5.3) wipes phone / phone_last4 → they must be NULL-able.
    op.alter_column("users", "phone", nullable=True)
    op.alter_column("users", "phone_last4", nullable=True)


def downgrade() -> None:
    # Do NOT restore NOT NULL on phone / dek_ciphertext here: rows written
    # under 0002 may be legitimately NULL (crypto-shredded accounts), and
    # re-asserting NOT NULL would fail on any such row. The column widening
    # in 0002 is effectively irreversible for existing data; an operator
    # re-running 0001 intentionally should first purge / backfill shredded
    # rows out of band.
    op.drop_column("users", "agreed_to_terms_at")
