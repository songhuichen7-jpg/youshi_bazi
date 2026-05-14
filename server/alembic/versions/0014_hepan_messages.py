"""Hepan: 邀请创建者 ↔ LLM 多轮对话表。

Revision ID: 0014_hepan_messages
Revises: 0013_hepan_soft_delete
Create Date: 2026-05-02 00:00:00

合盘从"一次性卡片 + 一次性 reading"演进成持续对话工具。每条 invite 最多
配一条线性对话，按 hepan_slug 索引。所以不需要单独的 conversation 表 ——
把 conversation 扁平地按 slug 分组，结构跟主 chat 的 conversations →
messages 比起来简化一层。

设计要点：
- ``content`` 是 EncryptedText (BYTEA) — 跟 messages.content 一样走 per-user
  DEK 加密。读写都得在 current_user 上下文里。
- ``role`` 限定 user / assistant — 合盘的 LLM 流不分 system/tool message
  存库（system 是 prompt 拼出来的，运行时算）。
- FK ondelete='CASCADE'：邀请被硬删（cron 30 天后清理）messages 跟着删。
  软删（deleted_at 非空）不连锁删 messages — A 撤销邀请但还能看历史对话。
- 复合索引 (hepan_slug, created_at) — 列表查询主路径。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0014_hepan_messages"
down_revision: Union[str, Sequence[str], None] = "0013_hepan_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hepan_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("hepan_slug", sa.String(length=12),
                  sa.ForeignKey("hepan_invites.slug", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=True),  # EncryptedText
        sa.Column("model_used", sa.String(length=32), nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('user','assistant')", name="hepan_messages_role_enum"),
    )
    op.create_index(
        "idx_hepan_messages_slug_created",
        "hepan_messages",
        ["hepan_slug", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_hepan_messages_slug_created", table_name="hepan_messages")
    op.drop_table("hepan_messages")
