"""Hepan invite: rewrite user_id to UUID FK + add reading_text columns.

Revision ID: 0011_hepan_user_id_uuid
Revises: 0010_drop_stale_plan_enum
Create Date: 2026-05-02 00:00:00

两件事一起做：

1) ``hepan_invites.user_id`` 原来是 ``BigInteger nullable`` —— Plan 4 早期写
   model 时还没敲定 user 主键类型，placeholder 留下来一直没回填。新的
   users 表主键是 UUID，对不上；把这列改成 ``UUID NULLABLE FK users(id)
   ON DELETE SET NULL``。NULL 仍然合法（B 侧匿名 / 老 invite 都没绑用户）。
   现存 5 行全是 NULL，drop + add 不丢数据。

2) ``hepan_invites`` 加上 LLM 完整解读的三列：
     reading_text          EncryptedText, NULL
     reading_version       VARCHAR(40), NULL  — prompt 改版后可以失效旧缓存
     reading_generated_at  timestamptz NULL
   合盘"完整解读"是付费档独占的 LLM 流式生成内容，缓存在这条 invite 上 —
   slug 是 cache key，pairs/dynamics 数据 + reading_version 是 cache 的失效信号。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0011_hepan_user_id_uuid"
down_revision: Union[str, Sequence[str], None] = "0010_drop_stale_plan_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) user_id: BigInteger → UUID FK
    #    存量 5 行全是 NULL，所以 drop + add 即可；无需迁移数据
    op.drop_column("hepan_invites", "user_id")
    op.add_column(
        "hepan_invites",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_hepan_invites_user", "hepan_invites", ["user_id"],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    # 2) 完整解读三列
    op.add_column(
        "hepan_invites",
        sa.Column("reading_text", sa.Text, nullable=True),    # EncryptedText 也走 Text 列
    )
    op.add_column(
        "hepan_invites",
        sa.Column("reading_version", sa.String(40), nullable=True),
    )
    op.add_column(
        "hepan_invites",
        sa.Column("reading_generated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hepan_invites", "reading_generated_at")
    op.drop_column("hepan_invites", "reading_version")
    op.drop_column("hepan_invites", "reading_text")
    op.drop_index("idx_hepan_invites_user", table_name="hepan_invites")
    op.drop_column("hepan_invites", "user_id")
    op.add_column(
        "hepan_invites",
        sa.Column("user_id", sa.BigInteger, nullable=True),
    )
