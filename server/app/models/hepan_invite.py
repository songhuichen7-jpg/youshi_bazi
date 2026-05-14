"""Hepan (合盘) invite record. One row per A-creates-invitation event.

Privacy notes:
  - For logged-in creators we store encrypted birth_input + paipan snapshots
    for both sides so the creator can later ask about the relationship in the
    main chat. Public reads never undefer those columns.
  - birth_hash columns are stored for de-duplication / abuse signals
    only — they are SHA-256 of the local birth tuple, not reversible.

Lifecycle:
  - status='pending' when A creates the invite (B not in yet).
  - status='completed' when B opens the link and submits their birth.
  - share_count tracks GET /api/hepan/{slug} hits for analytics.

Relationship to users:
  - ``user_id`` is set when A creates the invite while logged in. NULL when
    A is anonymous (or for old invites pre-0011). Used by ``GET /api/hepan/mine``.
  - B is never recorded — they may not even have an account.

LLM reading (Plan 5+):
  - ``reading_text`` 缓存"完整解读"流式生成的最终文本 (EncryptedText)。
  - ``reading_version`` 跟 prompt / pairs / dynamics 的版本号绑定，prompt 改版后
    旧 invite 的 reading 失效，下次 GET reading 时重新生成。
  - ``reading_generated_at`` 是落库时间，便于运维侧排查。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db_types import EncryptedJSONB, EncryptedText
from app.models import Base


class HepanInvite(Base):
    __tablename__ = "hepan_invites"

    slug: Mapped[str] = mapped_column(String(12), primary_key=True)

    # ── A side (always present) ────────────────────────────────────────
    a_birth_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    a_type_id: Mapped[str] = mapped_column(String(2), nullable=False)
    a_state: Mapped[str] = mapped_column(String(4), nullable=False)  # 绽放/蓄力
    a_day_stem: Mapped[str] = mapped_column(String(2), nullable=False)
    a_nickname: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # 创建者视角的加密上下文快照。公开 GET /api/hepan/{slug} 无 DEK，
    # 所以必须 deferred；只有创建者主 chat / 付费 reading/chat 才显式 undefer。
    a_birth_input: Mapped[Optional[dict]] = mapped_column(
        EncryptedJSONB, nullable=True, deferred=True,
    )
    a_paipan: Mapped[Optional[dict]] = mapped_column(
        EncryptedJSONB, nullable=True, deferred=True,
    )

    # ── B side (filled in after invitee submits) ───────────────────────
    b_birth_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    b_type_id: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    b_state: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    b_day_stem: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    b_nickname: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    b_birth_input: Mapped[Optional[dict]] = mapped_column(
        EncryptedJSONB, nullable=True, deferred=True,
    )
    b_paipan: Mapped[Optional[dict]] = mapped_column(
        EncryptedJSONB, nullable=True, deferred=True,
    )

    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")

    # ── Bookkeeping ────────────────────────────────────────────────────
    # 0011 之前是 BigInteger placeholder，没在用；现在跟 users.id (UUID) 对齐
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    share_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 软删 — 0013 加的；非空时所有读取端点 404。30 天后可硬删（cron 未做）
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── LLM 完整解读缓存 (Plan 5+) ──────────────────────────────────
    # deferred=True 关键 — 公开的 GET /api/hepan/{slug} 端点没 DEK 上下文，
    # 默认 SELECT * 含 reading_text 时会触发解密 → RuntimeError。延迟到访问
    # 才取，付费端点（POST /reading 走 current_user）已经把 DEK mount 了。
    reading_text: Mapped[Optional[str]] = mapped_column(
        EncryptedText, nullable=True, deferred=True,
    )
    reading_version: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    reading_generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
