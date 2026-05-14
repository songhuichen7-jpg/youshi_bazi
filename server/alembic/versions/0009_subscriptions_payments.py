"""Subscription + payment scaffolding (no payment provider yet).

Revision ID: 0009_subscriptions_payments
Revises: 0008_plan_lite_standard_pro
Create Date: 2026-05-01 00:00:00

These two tables exist so that, once 微信 / 支付宝 / Stripe 接入了，订阅历史
+ 个体支付事件能落到正经的表里，而不是脏在 ``users.plan_expires_at`` 上。
内测期间它们不被 webhook 喂数据 — 用一个 ``source='manual_grant'`` 的
入口让作者手动开通某个用户的 standard / pro。

设计要点：
- ``users.plan`` 仍然是 *cache* / 真相的衍生 — 服务里写 plan 是顺势改的，
  但订阅表是 "最权威的账单事实"。出问题时以订阅表反推。
- ``payments`` 在 ``raw_payload`` 里留了 jsonb，准备装下原始 webhook，便于
  后期对账；上线前会评估是否需要加密。
- ``subscriptions.provider_subscription_id`` UNIQUE 用于 webhook idempotent
  匹配（重复回调不会建多条订阅）。
- ends_at NULL 表示 "无明确到期"（人工开通常见）；status 'expired' 由 cron
  在 ends_at 到期后翻牌。
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0009_subscriptions_payments"
down_revision: Union[str, Sequence[str], None] = "0008_plan_lite_standard_pro"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        # NULL = 不设到期（人工开通常态）；非 NULL = 提供方约定的到期时间
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.Text, nullable=True),
        sa.Column("provider_subscription_id", sa.String(128), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("plan IN ('standard','pro')", name="subscriptions_plan_enum"),
        sa.CheckConstraint(
            "status IN ('active','canceled','expired','past_due')",
            name="subscriptions_status_enum",
        ),
        sa.CheckConstraint(
            "source IN ('manual_grant','wechat','alipay','stripe','app_store','play_store')",
            name="subscriptions_source_enum",
        ),
    )
    op.create_index("idx_subscriptions_user_status",
                    "subscriptions", ["user_id", "status"])
    # 部分索引：只为活动订阅建立，加速 "用户当前档位" 查询
    op.execute("""
        CREATE INDEX idx_subscriptions_active_user
        ON subscriptions (user_id)
        WHERE status = 'active'
    """)

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default=sa.text("'CNY'")),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_payment_id", sa.String(128), nullable=True, unique=True),
        sa.Column("raw_payload", postgresql.JSONB, nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('pending','succeeded','failed','refunded')",
            name="payments_status_enum",
        ),
        sa.CheckConstraint(
            "provider IN ('manual','wechat','alipay','stripe','app_store','play_store')",
            name="payments_provider_enum",
        ),
    )
    op.create_index("idx_payments_user_status", "payments", ["user_id", "status"])
    op.create_index("idx_payments_subscription", "payments", ["subscription_id"])


def downgrade() -> None:
    op.drop_index("idx_payments_subscription", table_name="payments")
    op.drop_index("idx_payments_user_status", table_name="payments")
    op.drop_table("payments")
    op.execute("DROP INDEX IF EXISTS idx_subscriptions_active_user")
    op.drop_index("idx_subscriptions_user_status", table_name="subscriptions")
    op.drop_table("subscriptions")
