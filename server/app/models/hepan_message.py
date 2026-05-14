"""Hepan multi-turn chat message — keyed by hepan_slug, per-user encrypted.

Created by 0014. The conversation is between the invite creator (A) and
the LLM, so all reads/writes happen in A's auth context — A's DEK
mounts before EncryptedText decrypt fires. Structure mirrors a slimmed-
down ``messages`` table (no conversation_id layer; one chat per slug).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Integer, String, text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db_types import EncryptedText
from app.models import Base


class HepanMessage(Base):
    __tablename__ = "hepan_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="hepan_messages_role_enum"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    hepan_slug: Mapped[str] = mapped_column(
        String(12),
        ForeignKey("hepan_invites.slug", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
