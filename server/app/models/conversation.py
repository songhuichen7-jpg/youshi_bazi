"""Conversation + message tables."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String, text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db_types import EncryptedJSONB, EncryptedText
from app.models import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True,
                                      server_default=text("gen_random_uuid()"))
    chart_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("charts.id", ondelete="RESTRICT"), nullable=False,
    )
    label: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    hepan_slug: Mapped[Optional[str]] = mapped_column(
        String(12),
        ForeignKey("hepan_invites.slug", ondelete="SET NULL"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=text("now()"))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','gua','cta')", name="role_enum"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True,
                                      server_default=text("gen_random_uuid()"))
    conversation_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(EncryptedJSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=text("now()"))


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"

    conversation_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    summary: Mapped[str] = mapped_column(EncryptedText, nullable=False)
    covered_message_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    covered_message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                  server_default=text("now()"))
