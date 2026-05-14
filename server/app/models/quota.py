"""quota_usage + llm_usage_logs tables."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class QuotaUsage(Base):
    __tablename__ = "quota_usage"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('chat_message','section_regen','verdicts_regen',"
            "'dayun_regen','liunian_regen','gua','sms_send')",
            name="kind_enum",
        ),
        UniqueConstraint("user_id", "period", "kind", name="uq_quota_usage_slot"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True,
                                      server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
    )
    period: Mapped[str] = mapped_column(String(10), nullable=False)  # 'YYYY-MM-DD'
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=text("now()"))


class LlmUsageLog(Base):
    __tablename__ = "llm_usage_logs"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True,
                                      server_default=text("gen_random_uuid()"))
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    chart_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("charts.id", ondelete="SET NULL"), nullable=True,
    )
    endpoint: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    intent: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=text("now()"))
