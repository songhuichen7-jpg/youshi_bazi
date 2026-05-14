"""Subscription + Payment ORM (Plan 5 / membership 1.0).

Both tables intentionally **don't** participate in user-data crypto-shred —
billing history is needed for accounting / refund / dispute reasons even
after a user 注销账号. ``user_id`` cascades on user delete though, so
real shred-of-account does sweep them; for soft-shred we'd need to revisit
this if 法务 wants the receipts to outlive the user.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String, Text, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "plan IN ('standard','pro')", name="subscriptions_plan_enum",
        ),
        CheckConstraint(
            "status IN ('active','canceled','expired','past_due')",
            name="subscriptions_status_enum",
        ),
        CheckConstraint(
            "source IN ('manual_grant','wechat','alipay','stripe','app_store','play_store')",
            name="subscriptions_source_enum",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    plan: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'active'"),
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    # NULL = open-ended（人工开通通常如此）；非 NULL = 渠道约定的到期点
    ends_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    canceled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Webhook idempotent 用 — 重复回调不会创建多条订阅
    provider_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','succeeded','failed','refunded')",
            name="payments_status_enum",
        ),
        CheckConstraint(
            "provider IN ('manual','wechat','alipay','stripe','app_store','play_store')",
            name="payments_provider_enum",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 一次付费可能不直接绑订阅（一次性买额度卡的场景）— 因此 nullable
    subscription_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 用整数 cents 避免浮点误差；CNY 显示时 / 100 即 ¥X.XX
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'CNY'"),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=True,
    )
    # Webhook 原始 payload — 对账 / 排查 / 退款时回看用
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
