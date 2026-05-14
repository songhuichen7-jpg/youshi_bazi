"""Add users.avatar_url for the user-center avatar feature.

Revision ID: 0007_user_avatar
Revises: 0006_classics_cache_guest
Create Date: 2026-05-01 00:00:00

Stores a relative path served via FastAPI's StaticFiles mount at
/static/avatars/, e.g. ``/static/avatars/<user_id>.webp``. Nullable —
users without a custom avatar fall back to the auto-generated initial
in the UI.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_user_avatar"
down_revision: Union[str, Sequence[str], None] = "0006_classics_cache_guest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
