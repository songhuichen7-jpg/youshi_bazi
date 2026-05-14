"""Session management: create / list / revoke / resolve cookie.

Cookie value is a raw 32-byte urlsafe token; DB stores sha256(token) only.
This means even a DB dump does not reveal active cookies.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserSession
from app.services.exceptions import SessionNotFoundError

# NOTE: spec §3 — 30-day rolling cookie.
_SESSION_TTL_DAYS = 30
_TOKEN_BYTES = 32


def _hash_token(raw: str) -> str:
    """sha256 hex of the raw cookie value."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _generate_token() -> str:
    """Raw 32-byte urlsafe token (Set-Cookie value)."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


async def create_session(
    db: AsyncSession,
    user_id: UUID,
    user_agent: str | None,
    ip: str | None,
) -> tuple[UserSession, str]:
    """Create a new session. Returns (db_row, raw_token_for_cookie)."""
    raw = _generate_token()
    now = datetime.now(tz=timezone.utc)
    row = UserSession(
        token_hash=_hash_token(raw),
        user_id=user_id,
        user_agent=user_agent,
        ip=ip,
        expires_at=now + timedelta(days=_SESSION_TTL_DAYS),
        last_seen_at=now,
    )
    db.add(row)
    await db.flush()
    return row, raw


async def resolve_session(db: AsyncSession, raw_token: str) -> UserSession | None:
    """Look up a session by raw cookie value. Returns None if not found /
    expired; caller decides between 401 and silent fallback.
    """
    token_hash = _hash_token(raw_token)
    stmt = select(UserSession).where(
        UserSession.token_hash == token_hash,
        UserSession.expires_at > datetime.now(tz=timezone.utc),
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def touch_session(db: AsyncSession, session_id: UUID) -> None:
    """Slide the 30-day window + update last_seen_at."""
    now = datetime.now(tz=timezone.utc)
    await db.execute(
        update(UserSession)
        .where(UserSession.id == session_id)
        .values(
            last_seen_at=now,
            expires_at=now + timedelta(days=_SESSION_TTL_DAYS),
        )
    )


async def list_sessions(
    db: AsyncSession,
    user_id: UUID,
) -> list[UserSession]:
    """All unexpired sessions for this user, newest-activity first."""
    stmt = (
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.expires_at > datetime.now(tz=timezone.utc),
        )
        .order_by(UserSession.last_seen_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def revoke_session(
    db: AsyncSession,
    user_id: UUID,
    session_id: UUID,
) -> None:
    """Revoke one of the user's own sessions. Raises SessionNotFoundError if
    the id doesn't belong to this user (privacy: don't distinguish
    'not yours' from 'doesn't exist' — both surface as 404)."""
    result = await db.execute(
        delete(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
        )
    )
    if result.rowcount == 0:
        raise SessionNotFoundError()


async def revoke_all_sessions(db: AsyncSession, user_id: UUID) -> int:
    """Revoke every session for this user (used by shred_account)."""
    result = await db.execute(
        delete(UserSession).where(UserSession.user_id == user_id)
    )
    return result.rowcount
