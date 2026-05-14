"""SMS send + verify + rate limit business logic.

Uses sms_codes table as both rate-limit store and code store. Code is stored
as sha256 hash (no salt — 6 digits + 5-minute expiry makes rainbow-table
attacks uneconomical, and the added latency to every verify is not worth it).

Rate limits (spec §2.1):
  - 60s cooldown per phone
  - 5/hour per phone
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.quotas import QUOTAS
from app.models.user import SmsCode, User
from app.services.exceptions import (
    SmsCodeInvalidError,
    SmsCooldownError,
    SmsHourlyLimitError,
)
from app.services.quota import QuotaTicket

# NOTE: spec §2.1 — rate limit constants.
_COOLDOWN_SECONDS = 60
_HOURLY_LIMIT = 5
_EXPIRY_MINUTES = 5
_MAX_ATTEMPTS = 5

SmsPurpose = Literal["register", "login", "bind"]


@dataclass(frozen=True)
class SmsSendResult:
    code: str           # raw 6-digit code (caller decides whether to echo it)
    expires_at: datetime


def _hash_code(code: str) -> str:
    """SHA-256 hex of the raw code. No salt — see module docstring."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    """Return a zero-padded 6-digit numeric string."""
    return "{:06d}".format(secrets.randbelow(1_000_000))


async def _check_rate_limit(db: AsyncSession, phone: str) -> None:
    """Raise SmsCooldownError / SmsHourlyLimitError on violation."""
    # NOTE: spec §2.1 — 60s cooldown.
    cooldown_row = await db.execute(text("""
        SELECT EXTRACT(EPOCH FROM (now() - max(created_at))) AS elapsed
          FROM sms_codes
         WHERE phone = :phone
           AND created_at > now() - make_interval(secs => :cooldown)
    """), {"phone": phone, "cooldown": _COOLDOWN_SECONDS})
    r = cooldown_row.first()
    if r is not None and r[0] is not None:
        retry_after = int(_COOLDOWN_SECONDS - r[0])
        if retry_after < 1:
            retry_after = 1
        raise SmsCooldownError(
            details={"retry_after": retry_after},
        )

    # NOTE: spec §2.1 — 5 per hour.
    hourly_row = await db.execute(text("""
        SELECT count(*) FROM sms_codes
         WHERE phone = :phone
           AND created_at > now() - interval '1 hour'
    """), {"phone": phone})
    count = hourly_row.scalar_one()
    if count >= _HOURLY_LIMIT:
        raise SmsHourlyLimitError(
            details={"limit": _HOURLY_LIMIT, "retry_after": 3600},
        )


async def send_sms_code(
    db: AsyncSession,
    phone: str,
    purpose: SmsPurpose,
    ip: str | None,
    provider_send,  # signature: async (phone, code) -> None
    *,
    user: User | None = None,
) -> SmsSendResult:
    """Generate a fresh code, insert it, call provider.send, return the code.

    If `user` is given, also charges one `sms_send` quota slot. Registration
    path does NOT pass user (quota can't be charged before the row exists).

    Caller must then commit the session (api layer). If provider.send raises,
    caller should let the transaction roll back naturally.
    """
    await _check_rate_limit(db, phone)

    # NOTE: charge sms_send quota ONLY when caller provides the authenticated user
    # (login resend, phone-change flows). Registration path passes user=None so
    # this block is skipped — user row doesn't exist yet.
    ticket: QuotaTicket | None = None
    if user is not None:
        sms_limit = QUOTAS.get(user.plan, QUOTAS["free"])["sms_send"]
        ticket = QuotaTicket(user=user, kind="sms_send", limit=sms_limit, _db=db)

    code = _generate_code()
    code_hash = _hash_code(code)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(minutes=_EXPIRY_MINUTES)

    row = SmsCode(
        phone=phone,
        code_hash=code_hash,
        purpose=purpose,
        expires_at=expires_at,
        ip=ip,
    )
    db.add(row)
    await db.flush()

    # provider.send is called LAST so any error aborts the whole transaction.
    await provider_send(phone, code)

    # Commit quota only after provider.send succeeds. ticket.commit is atomic;
    # races are rare here because SMS is rate-limited on the same table.
    if ticket is not None:
        try:
            await ticket.commit()
        except Exception:  # noqa: BLE001 — quota race; SMS already went out; best-effort
            pass

    return SmsSendResult(code=code, expires_at=expires_at)


async def verify_sms_code(
    db: AsyncSession,
    phone: str,
    code: str,
    purpose: SmsPurpose,
) -> None:
    """Raises SmsCodeInvalidError on any failure. Burns the row on 5 attempts."""
    stmt = (
        select(SmsCode)
        .where(
            SmsCode.phone == phone,
            SmsCode.purpose == purpose,
            SmsCode.used_at.is_(None),
            SmsCode.expires_at > datetime.now(tz=timezone.utc),
        )
        .order_by(SmsCode.created_at.desc())
        .limit(1)
    )
    row: SmsCode | None = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise SmsCodeInvalidError("验证码不存在或已过期")

    if _hash_code(code) != row.code_hash:
        # attempts++; if reaches max, burn the row.
        new_attempts = row.attempts + 1
        row.attempts = new_attempts
        if new_attempts >= _MAX_ATTEMPTS:
            row.used_at = datetime.now(tz=timezone.utc)
            await db.flush()
            raise SmsCodeInvalidError(
                "验证码错误次数过多，请重新获取",
                details={"attempts_left": 0, "burned": True},
            )
        await db.flush()
        raise SmsCodeInvalidError(
            "验证码错误",
            details={"attempts_left": _MAX_ATTEMPTS - new_attempts},
        )

    # success — mark used so it can't be reused
    row.used_at = datetime.now(tz=timezone.utc)
    await db.flush()
