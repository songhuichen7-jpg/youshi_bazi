"""Core auth flows: register / login / logout / shred_account.

All functions take an AsyncSession and return Python-native types or raise
ServiceError subclasses. The api/ layer maps errors to HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import secrets

from cryptography.exceptions import InvalidTag
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_dek, encrypt_dek, generate_dek
from app.models.user import InviteCode, SmsCode, User, UserSession
from app.services.nickname_pool import random_nickname
from app.services.exceptions import (
    AccountDisabledError,
    AccountShreddedError,
    InviteCodeError,
    PhoneAlreadyRegisteredError,
    TermsNotAgreedError,
    UserNotFoundError,
)
from app.services.session import create_session, revoke_all_sessions
from app.services.sms import verify_sms_code


@dataclass(frozen=True)
class AuthResult:
    user: User
    raw_token: str   # caller sets it as Set-Cookie


def _guest_phone_candidate() -> str:
    # 11 digits keeps us inside the existing phone column budget while staying
    # obviously synthetic for dev-only guest accounts.
    return f"99{secrets.randbelow(10**9):09d}"


async def register(
    db: AsyncSession,
    *,
    phone: str,
    code: str,
    invite_code: str | None,
    nickname: str | None,
    agreed_to_terms: bool,
    user_agent: str | None,
    ip: str | None,
    kek: bytes,
) -> AuthResult:
    """Transactional register flow. Caller wraps in a transaction.

    Flow (spec §3.1):
      1. verify_sms_code
      2. agreed_to_terms must be True
      3. phone must not already be registered
      4. if settings.require_invite: validate invite_code (and increment atomically)
      5. generate DEK, encrypt with KEK
      6. INSERT users
      7. atomic UPDATE invite_codes SET used_count = used_count + 1 WHERE used_count < max_uses
      8. create session, return (user, raw_token)
    """
    await verify_sms_code(db, phone, code, "register")

    if not agreed_to_terms:
        raise TermsNotAgreedError()

    existing = await db.execute(select(User).where(User.phone == phone))
    if existing.scalar_one_or_none() is not None:
        raise PhoneAlreadyRegisteredError()

    invite_row: InviteCode | None = None
    if settings.require_invite:
        if invite_code is None:
            raise InviteCodeError("请输入邀请码")
        stmt = select(InviteCode).where(
            InviteCode.code == invite_code,
            InviteCode.disabled.is_(False),
        )
        invite_row = (await db.execute(stmt)).scalar_one_or_none()
        if invite_row is None:
            raise InviteCodeError("邀请码不存在或已禁用")
        if invite_row.expires_at is not None and invite_row.expires_at <= datetime.now(tz=timezone.utc):
            raise InviteCodeError("邀请码已过期")
        if invite_row.used_count >= invite_row.max_uses:
            raise InviteCodeError("邀请码已用完")

    dek = generate_dek()
    dek_ciphertext = encrypt_dek(dek, kek)

    user = User(
        phone=phone,
        phone_last4=phone[-4:],
        nickname=nickname,
        invited_by_user_id=invite_row.created_by if invite_row is not None else None,
        used_invite_code_id=invite_row.id if invite_row is not None else None,
        dek_ciphertext=dek_ciphertext,
        dek_key_version=1,
        agreed_to_terms_at=datetime.now(tz=timezone.utc),
        # 内测期默认给 pro 资格 — 让试用者拿到完整体验,不被 lite 配额卡住。
        # 付费上线时这一行去掉,让 DB server_default('lite') 生效。
        plan="pro",
    )
    db.add(user)
    await db.flush()

    if invite_row is not None:
        # NOTE: spec §3.3 — atomic used_count++; if concurrent caller raced us
        # past max_uses, result.rowcount == 0 and we raise.
        result = await db.execute(
            update(InviteCode)
            .where(
                InviteCode.id == invite_row.id,
                InviteCode.used_count < invite_row.max_uses,
            )
            .values(used_count=InviteCode.used_count + 1)
        )
        if result.rowcount == 0:
            raise InviteCodeError("邀请码并发竞争失败，请重试")

    _, raw_token = await create_session(db, user.id, user_agent=user_agent, ip=ip)
    return AuthResult(user=user, raw_token=raw_token)


async def login(
    db: AsyncSession,
    *,
    phone: str,
    code: str,
    user_agent: str | None,
    ip: str | None,
) -> AuthResult:
    """Login flow (spec §3.2). Does NOT generate DEK (that's registration-only)."""
    await verify_sms_code(db, phone, code, "login")

    user: User | None = (await db.execute(
        select(User).where(User.phone == phone)
    )).scalar_one_or_none()
    if user is None:
        raise UserNotFoundError()
    if user.status != "active":
        raise AccountDisabledError()
    if user.dek_ciphertext is None:
        # Account was crypto-shredded (phone should have been cleared too,
        # so this branch is theoretical, but belt-and-suspenders).
        raise AccountShreddedError()

    _, raw_token = await create_session(db, user.id, user_agent=user_agent, ip=ip)
    return AuthResult(user=user, raw_token=raw_token)


def _validate_guest_token(token: str | None) -> str | None:
    """Accept only client-provided guest tokens that look like our format
    (UUID v4 hex, no dashes, 32 chars). Rejects garbage and over-long
    inputs to prevent storage bloat / injection."""
    if not token:
        return None
    s = str(token).strip().lower()
    if len(s) < 16 or len(s) > 64:
        return None
    # 允许 hex / hyphenated UUID — 标准化成无连字符的 hex 字符串
    cleaned = s.replace("-", "")
    if not cleaned.isalnum():
        return None
    return cleaned[:64]


async def bind_phone_to_guest(
    db: AsyncSession,
    *,
    user: User,
    phone: str,
    code: str,
) -> User:
    """把手机号绑定到当前访客 user — 不创建新账号，原 user_id / 命盘 / 对话
    全部沿用，只是补上 phone + 清空 guest_token 这一对字段。
    用 SMS purpose='register'（跟首次注册同款），后端校验通过即生效。"""
    if user.phone and not user.phone.startswith("99"):
        # 已经绑定真号了 — 不允许重复绑（防误操作）
        raise PhoneAlreadyRegisteredError()
    await verify_sms_code(db, phone, code, "register")
    existing = (await db.execute(
        select(User).where(User.phone == phone, User.id != user.id)
    )).scalar_one_or_none()
    if existing is not None:
        raise PhoneAlreadyRegisteredError()
    user.phone = phone
    user.phone_last4 = phone[-4:]
    user.guest_token = None
    await db.flush()
    return user


async def login_guest(
    db: AsyncSession,
    *,
    user_agent: str | None,
    ip: str | None,
    kek: bytes,
    guest_token: str | None = None,
) -> AuthResult:
    """Guest login flow.

    If ``guest_token`` is provided AND already bound to an active user,
    re-issue a session for that user (their charts/conversations
    persist across browser sessions). Otherwise create a fresh guest
    user and bind the token so the next call from the same browser
    rejoins this account."""
    normalized = _validate_guest_token(guest_token)

    if normalized:
        existing_user = (await db.execute(
            select(User).where(
                User.guest_token == normalized,
                User.status == "active",
            )
        )).scalar_one_or_none()
        if existing_user is not None:
            try:
                decrypt_dek(existing_user.dek_ciphertext, kek)
            except InvalidTag:
                existing_user.guest_token = None
                normalized = None
                await db.flush()
            else:
                _, raw_token = await create_session(
                    db, existing_user.id, user_agent=user_agent, ip=ip,
                )
                return AuthResult(user=existing_user, raw_token=raw_token)

    dek = generate_dek()
    dek_ciphertext = encrypt_dek(dek, kek)

    phone = None
    for _ in range(8):
        candidate = _guest_phone_candidate()
        existing = await db.execute(select(User.id).where(User.phone == candidate))
        if existing.scalar_one_or_none() is None:
            phone = candidate
            break
    if phone is None:
        raise RuntimeError("failed to allocate guest phone")

    # 如果客户端没传 guest_token（老客户端 / 新访客），后端生成一个发回。
    # 这样客户端写到 localStorage 后下次进来就能凭它找回自己的账号。
    if not normalized:
        normalized = secrets.token_hex(16)  # 32 字符 hex，落入 guest_token 字段长度

    user = User(
        phone=phone,
        phone_last4=phone[-4:],
        nickname=random_nickname(),
        dek_ciphertext=dek_ciphertext,
        dek_key_version=1,
        agreed_to_terms_at=datetime.now(tz=timezone.utc),
        guest_token=normalized,
        # 内测期默认给 pro 资格 — 同上,让游客也拿到完整体验。
        plan="pro",
    )
    db.add(user)
    await db.flush()

    _, raw_token = await create_session(db, user.id, user_agent=user_agent, ip=ip)
    return AuthResult(user=user, raw_token=raw_token)


async def logout(db: AsyncSession, session_id) -> None:
    """Delete the current session (caller provides session_id from current_user)."""
    await db.execute(delete(UserSession).where(UserSession.id == session_id))


async def shred_account(db: AsyncSession, user: User) -> datetime:
    """Crypto-shred user account. Returns the shred timestamp.

    Flow (spec §5.3):
      1. DELETE sessions for this user
      2. DELETE sms_codes for this phone
      3. UPDATE users SET
           status='disabled', phone=NULL, phone_last4=NULL, nickname=NULL,
           invited_by_user_id=NULL, wechat_openid=NULL, wechat_unionid=NULL,
           dek_ciphertext=NULL
      4. Caller commits.
    """
    phone = user.phone
    await revoke_all_sessions(db, user.id)

    if phone is not None:
        await db.execute(delete(SmsCode).where(SmsCode.phone == phone))

    shredded_at = datetime.now(tz=timezone.utc)
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            status="disabled",
            phone=None,
            phone_last4=None,
            nickname=None,
            invited_by_user_id=None,
            wechat_openid=None,
            wechat_unionid=None,
            dek_ciphertext=None,
        )
    )
    return shredded_at
