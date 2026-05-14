"""Card share record: one row per card-generation event.
Stores minimal info needed to render a preview when someone opens the share link."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class CardShare(Base):
    __tablename__ = "card_shares"

    slug: Mapped[str] = mapped_column(String(12), primary_key=True)
    birth_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    type_id: Mapped[str] = mapped_column(String(2), nullable=False)
    cosmic_name: Mapped[str] = mapped_column(String(20), nullable=False)
    suffix: Mapped[str] = mapped_column(String(30), nullable=False)
    nickname: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    share_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
