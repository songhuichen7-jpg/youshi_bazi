"""Anonymous event tracking. One row per tracked frontend event."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    type_id: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    channel: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    from_param: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    share_slug: Mapped[Optional[str]] = mapped_column(String(12), nullable=True, index=True)
    anonymous_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    user_id: Mapped[Optional[UUID]] = mapped_column(PgUUID(as_uuid=True), nullable=True, index=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    viewport: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )
