"""Hepan invite: soft-delete column + active-row index.

Revision ID: 0013_hepan_soft_delete
Revises: 0012_hepan_reading_text_bytea
Create Date: 2026-05-02 00:00:00

发出去的邀请链接是公共可分享的资产，A 想撤销时不能粗暴硬删（B 那边可能
还揣着链接）。改用软删 — ``deleted_at`` 非空时所有读取端点 (GET /{slug},
POST /complete, /reading, /mine) 都拒绝。30 天后再硬删可以走清理 cron，
现阶段先支持软删本身。

新增部分索引 ``idx_hepan_invites_active_user``：``WHERE deleted_at IS NULL``
+ user_id ASC — /api/hepan/mine 的查询 (where user_id=$1 and deleted_at
is null order by created_at desc) 主路径走这条。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0013_hepan_soft_delete"
down_revision: Union[str, Sequence[str], None] = "0012_hepan_reading_text_bytea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hepan_invites",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # 0011 加的 idx_hepan_invites_user 已经是 partial WHERE user_id IS NOT NULL；
    # 这里再加一条 partial WHERE deleted_at IS NULL — /mine 查询命中得更精准。
    op.execute("""
        CREATE INDEX idx_hepan_invites_active_user
        ON hepan_invites (user_id, created_at DESC)
        WHERE deleted_at IS NULL AND user_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_hepan_invites_active_user")
    op.drop_column("hepan_invites", "deleted_at")
