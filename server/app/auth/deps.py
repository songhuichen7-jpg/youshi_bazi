"""Auth dependencies — real implementations (Plan 3).

Signature contract from Plan 2 is preserved:
    current_user(request, db=Depends(get_db)) -> User
    optional_user(request, db=Depends(get_db)) -> User | None
    require_admin(user=Depends(current_user)) -> User
    check_quota(kind: str) -> dependency callable -> QuotaTicket

DEK mounting: current_user decrypts the user's DEK and sets the contextvar
from app.db_types so EncryptedText / EncryptedJSONB columns work for the
rest of the request.
"""
from __future__ import annotations

import hashlib
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from cryptography.exceptions import InvalidTag
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_dek
from app.core.db import get_db
from app.core.quotas import QUOTAS, next_midnight_beijing, seconds_until_midnight, today_beijing
from app.db_types import _current_dek  # type: ignore[attr-defined]
from app.models.user import User, UserSession
from app.services.quota import QuotaTicket


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def _authenticate_and_mount_dek(
    request: Request,
    db: AsyncSession,
) -> tuple[User, object]:
    """Shared validation used by current_user + optional_user yield-deps.

    Returns (user, dek_reset_token). Caller MUST call `_current_dek.reset(token)`
    in a `finally` block after the request completes, to prevent the contextvar
    from leaking across task boundaries (even though asyncio per-task isolation
    is the current safety net, this makes the invariant explicit).
    """
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(401, detail={"code": "UNAUTHORIZED", "message": "未登录", "details": None})

    token_hash = _sha256(token)
    session_row: UserSession | None = (await db.execute(
        select(UserSession).where(UserSession.token_hash == token_hash)
    )).scalar_one_or_none()
    if session_row is None:
        raise HTTPException(401, detail={"code": "SESSION_INVALID", "message": "会话无效", "details": None})
    if session_row.expires_at <= datetime.now(tz=timezone.utc):
        raise HTTPException(401, detail={"code": "SESSION_EXPIRED", "message": "会话已过期", "details": None})

    user: User | None = await db.get(User, session_row.user_id)
    if user is None:
        raise HTTPException(401, detail={"code": "USER_NOT_FOUND", "message": "用户不存在", "details": None})
    if user.status != "active":
        raise HTTPException(401, detail={"code": "ACCOUNT_DISABLED", "message": "账号已停用", "details": None})
    if user.dek_ciphertext is None:
        raise HTTPException(401, detail={"code": "ACCOUNT_SHREDDED", "message": "账号已注销", "details": None})

    # Decrypt DEK and mount into request-scoped contextvar.
    kek = request.app.state.kek
    try:
        dek = decrypt_dek(user.dek_ciphertext, kek)
    except InvalidTag:
        raise HTTPException(
            401,
            detail={
                "code": "SESSION_CRYPTO_INVALID",
                "message": "登录状态已失效，请重新进入",
                "details": None,
            },
        ) from None
    dek_token = _current_dek.set(dek)
    try:
        request.state.session = session_row
        # Rolling 30-day expiry.
        now = datetime.now(tz=timezone.utc)
        await db.execute(
            text("""
                UPDATE sessions
                   SET last_seen_at = :now,
                       expires_at = :exp
                 WHERE id = :sid
            """),
            {"now": now, "exp": now + timedelta(days=30), "sid": session_row.id},
        )
        # Release the sessions row lock before the business handler runs.
        #
        # Some authenticated endpoints stream or call LLMs for tens of seconds.
        # If the rolling-expiry UPDATE stayed in the request transaction, every
        # concurrent request from the same browser session would block in auth
        # behind this row lock. Hepan's short /mine and /invite calls are
        # especially sensitive to that because users click them while chart
        # bootstrap is still doing background work.
        await db.commit()
    except BaseException:  # noqa: BLE001 — must reset contextvar before propagating
        _current_dek.reset(dek_token)
        raise

    return user, dek_token


async def current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[User, None]:
    """Yield-dep: validate session, mount DEK contextvar, reset on teardown."""
    user, dek_token = await _authenticate_and_mount_dek(request, db)
    try:
        yield user
    finally:
        _current_dek.reset(dek_token)


async def optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[User | None, None]:
    """Returns None for guests (no cookie). A present-but-invalid cookie still
    raises 401 — it's an error signal, not 'anonymous'.

    Yield-dep so the DEK contextvar is reset on teardown even for guest requests."""
    if "session" not in request.cookies:
        yield None
        return
    user, dek_token = await _authenticate_and_mount_dek(request, db)
    try:
        yield user
    finally:
        _current_dek.reset(dek_token)


async def public_optional_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AsyncGenerator[User | None, None]:
    """Like optional_user but a stale/invalid session cookie is treated as
    anonymous instead of raising 401.

    Use for public share endpoints (hepan invite link, card share) where the
    visitor's browser may carry a stale cookie from a prior logged-out session
    or another account. The contract there is "anyone can see this", so a
    bad cookie shouldn't break the link — just degrade to anonymous."""
    if "session" not in request.cookies:
        yield None
        return
    try:
        user, dek_token = await _authenticate_and_mount_dek(request, db)
    except HTTPException:
        yield None
        return
    try:
        yield user
    finally:
        _current_dek.reset(dek_token)


# require_admin and check_quota remain unchanged — they call `Depends(current_user)`
# which FastAPI handles transparently across both plain-async and yield-dep patterns.

async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            403,
            detail={"code": "FORBIDDEN_ADMIN_ONLY", "message": "需要管理员权限", "details": None},
        )
    return user


def check_quota(kind: str):
    """Quota-ticket factory. Pre-checks current count; raises 429 if full.
    On success returns a QuotaTicket the caller commits after business work.
    """
    async def _dep(
        user: User = Depends(current_user),
        db: AsyncSession = Depends(get_db),
    ) -> QuotaTicket:
        limit = QUOTAS[user.plan][kind]
        period = today_beijing()

        row = (await db.execute(text("""
            SELECT count FROM quota_usage
             WHERE user_id = :uid AND period = :period AND kind = :kind
        """), {"uid": user.id, "period": period, "kind": kind})).first()
        used = row[0] if row is not None else 0
        if used >= limit:
            raise HTTPException(
                429,
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "message": f"今日 {kind} 配额已用完",
                    "details": {
                        "kind": kind,
                        "limit": limit,
                        "resets_at": next_midnight_beijing().isoformat(),
                    },
                },
                headers={"Retry-After": str(seconds_until_midnight())},
            )
        return QuotaTicket(user=user, kind=kind, limit=limit, _db=db)

    return _dep
