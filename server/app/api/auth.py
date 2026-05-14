"""HTTP layer for /api/auth/*. Thin wrapper over services/*."""
from __future__ import annotations

import io
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.core.config import settings
from app.core.db import get_db
from app.models.hepan_invite import HepanInvite
from app.models.user import User
from app.schemas.auth import (
    AccountDeleteRequest,
    AccountDeleteResponse,
    BindPhoneRequest,
    GuestLoginRequest,
    LoginRequest,
    MeResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    SmsSendRequest,
    SmsSendResponse,
    UserResponse,
)
from app.services import auth as auth_service
from app.services import sms as sms_service
from app.services.exceptions import ServiceError
from app.sms import get_sms_provider

router = APIRouter(prefix="/api/auth", tags=["auth"])

# NOTE: spec §3 — 30-day cookie.
_COOKIE_NAME = "session"
_COOKIE_MAX_AGE = 30 * 24 * 3600


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=raw_token,
        max_age=_COOKIE_MAX_AGE,
        path="/",
        httponly=True,
        secure=settings.resolved_session_cookie_secure,
        samesite="lax",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(_COOKIE_NAME, path="/")


def _user_response(user: User) -> UserResponse:
    # Defensive: shredded users have phone_last4=None; never surface.
    return UserResponse(
        id=user.id,
        phone_last4=user.phone_last4 or "",
        nickname=user.nickname,
        avatar_url=user.avatar_url,
        role=user.role,
        plan=user.plan,
        plan_expires_at=user.plan_expires_at,
        onboarded_at=user.onboarded_at,
        created_at=user.created_at,
    )


def _http_error(err: ServiceError) -> HTTPException:
    detail = err.to_dict()
    headers = None
    if "retry_after" in err.details:
        headers = {"Retry-After": str(err.details["retry_after"])}
    return HTTPException(status_code=err.status, detail=detail, headers=headers)


@router.post("/sms/send", response_model=SmsSendResponse, response_model_by_alias=True)
async def sms_send_endpoint(
    body: SmsSendRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SmsSendResponse:
    try:
        result = await sms_service.send_sms_code(
            db,
            phone=body.phone,
            purpose=body.purpose,
            ip=request.client.host if request.client else None,
            provider_send=get_sms_provider().send,
        )
    except ServiceError as e:
        raise _http_error(e)

    response = SmsSendResponse(expires_in=300)
    if settings.env == "dev":
        # NOTE: dev echo only. Prod never exposes this field.
        response = SmsSendResponse(expires_in=300, devCode=result.code)
    return response


@router.post("/register")
async def register_endpoint(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await auth_service.register(
            db,
            phone=body.phone,
            code=body.code,
            invite_code=body.invite_code,
            nickname=body.nickname,
            agreed_to_terms=body.agreed_to_terms,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
            kek=request.app.state.kek,
        )
    except ServiceError as e:
        raise _http_error(e)

    _set_session_cookie(response, result.raw_token)
    return {"user": _user_response(result.user).model_dump(mode="json")}


@router.post("/login")
async def login_endpoint(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await auth_service.login(
            db,
            phone=body.phone,
            code=body.code,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except ServiceError as e:
        raise _http_error(e)

    _set_session_cookie(response, result.raw_token)
    return {"user": _user_response(result.user).model_dump(mode="json")}


@router.post("/guest")
async def guest_login_endpoint(
    request: Request,
    response: Response,
    body: GuestLoginRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not settings.guest_login_available:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Not found"})

    result = await auth_service.login_guest(
        db,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
        kek=request.app.state.kek,
        guest_token=body.guest_token if body is not None else None,
    )
    await db.commit()
    _set_session_cookie(response, result.raw_token)
    return {
        "user": _user_response(result.user).model_dump(mode="json"),
        # 回传给前端：第一次进入时后端可能根据传入 token 返回已存在的
        # 用户（这种情况 guest_token 等于客户端传入的）；新建账号时返回
        # 同样的 token 让客户端写到 localStorage。两种情况下值都是 user
        # 在 DB 里的 guest_token 字段。
        "guest_token": result.user.guest_token,
    }


@router.post("/logout")
async def logout_endpoint(
    request: Request,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = request.state.session
    await auth_service.logout(db, session.id)
    _clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me_endpoint(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """Auth + 当日配额快照。Plan 3 留的 ``quota_snapshot={}`` 占位现在
    实填了：直接走 services.quota.get_snapshot 拿当日 7 个 kind 的 used/limit/
    resets_at + 命盘上限。前端的"本月用量" UI 直接读这里。"""
    from app.services.quota import get_snapshot
    from sqlalchemy import select as _select, func as _func
    from app.models.chart import Chart
    from app.core.quotas import chart_max_for

    snapshot = await get_snapshot(db, user)
    chart_count = (await db.execute(
        _select(_func.count(Chart.id)).where(
            Chart.user_id == user.id,
            Chart.deleted_at.is_(None),
        )
    )).scalar_one()

    snap_dict = snapshot.model_dump(mode="json")
    # 命盘是累计型上限，不在 daily QuotaResponse 里 — 单独一项塞进去。
    # 前端把 chart 跟 chat_message / gua 一起渲染成进度条。
    snap_dict["chart"] = {
        "used": int(chart_count),
        "limit": chart_max_for(user.plan),
        "resets_at": None,    # 命盘不日重置
    }
    return MeResponse(user=_user_response(user), quota_snapshot=snap_dict)


@router.post("/bind-phone", response_model=UserResponse)
async def bind_phone_endpoint(
    body: BindPhoneRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """访客升级到正式账号 — 把手机号绑到当前 user 上，不换 user_id，
    原命盘 / 对话 / 古籍缓存全部沿用。"""
    try:
        updated = await auth_service.bind_phone_to_guest(
            db, user=user, phone=body.phone, code=body.code,
        )
        await db.commit()
    except ServiceError as e:
        await db.rollback()
        raise _http_error(e)
    return _user_response(updated)


@router.get("/export")
async def export_data_endpoint(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """打包用户的命盘 + 对话 + 消息为 JSON。客户端拿到自行下载。
    访客升级 / 换设备前的"备份"，也是数据携带权（GDPR-style）的兑现。
    Conversation 没有 user_id，通过 chart_id 反查；同样地 Message 经
    conversation_id 串联。EncryptedText 列由 SQLAlchemy 解密好再写到 dict。"""
    from sqlalchemy import select as _select
    from app.models.chart import Chart
    from app.models.conversation import Conversation, Message

    charts_rows = (await db.execute(
        _select(Chart)
        .where(Chart.user_id == user.id, Chart.deleted_at.is_(None))
        .order_by(Chart.created_at)
    )).scalars().all()
    chart_ids = [c.id for c in charts_rows]

    convs_rows = []
    msgs_rows = []
    if chart_ids:
        convs_rows = (await db.execute(
            _select(Conversation)
            .where(
                Conversation.chart_id.in_(chart_ids),
                Conversation.deleted_at.is_(None),
            )
            .order_by(Conversation.created_at)
        )).scalars().all()
        conv_ids = [c.id for c in convs_rows]
        if conv_ids:
            msgs_rows = (await db.execute(
                _select(Message)
                .where(Message.conversation_id.in_(conv_ids))
                .order_by(Message.created_at)
            )).scalars().all()

    return {
        "exported_at": datetime.now(tz=timezone.utc).isoformat(),
        "user": _user_response(user).model_dump(mode="json"),
        "charts": [
            {
                "id": str(c.id),
                "label": c.label,
                "birth_input": c.birth_input,
                "paipan": c.paipan,
                "engine_version": c.engine_version,
                "created_at": c.created_at.isoformat(),
            }
            for c in charts_rows
        ],
        "conversations": [
            {
                "id": str(c.id),
                "chart_id": str(c.chart_id) if c.chart_id else None,
                "label": c.label,
                "created_at": c.created_at.isoformat(),
            }
            for c in convs_rows
        ],
        "messages": [
            {
                "id": str(m.id),
                "conversation_id": str(m.conversation_id),
                "role": m.role,
                "content": m.content,
                "meta": m.meta,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs_rows
        ],
    }


# 头像写入目录 — 跟 media-cache / classics 索引一起放在 server/var 下
_AVATAR_DIR = Path(__file__).resolve().parents[2] / "var" / "avatars"
_AVATAR_MAX_BYTES = 4 * 1024 * 1024     # 4MB 上限够手机随手拍的截图
_AVATAR_OUTPUT_SIZE = 256                # 头像最终边长（正方形）
_ALLOWED_MIME = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})


@router.patch("/me", response_model=UserResponse)
async def update_profile_endpoint(
    body: ProfileUpdateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """更新昵称 / 头像 URL / mark onboarded。所有字段可选。
    nickname 改时同事务 cascade 到 hepan_invites.a_nickname。
    mark_onboarded=True 时 server 写 onboarded_at（仅在还是 NULL 时——
    重复调不会覆盖，避免引导后用户改名又触发新 onboarded_at 写入）。"""
    changed = False
    if body.nickname is not None:
        cleaned = body.nickname.strip()
        if cleaned and len(cleaned) > 40:
            raise HTTPException(
                status_code=400,
                detail={"code": "VALIDATION", "message": "昵称最长 40 个字符"},
            )
        new_nick = cleaned or None
        if new_nick != user.nickname:
            user.nickname = new_nick
            # Cascade to all of this user's hepan_invites snapshots.
            # Only `a_nickname` — schema has no `b_user_id` (B is filled
            # anonymously per current invite contract).
            await db.execute(
                update(HepanInvite)
                .where(
                    HepanInvite.user_id == user.id,
                    HepanInvite.deleted_at.is_(None),
                )
                .values(a_nickname=new_nick)
            )
        changed = True
    if body.avatar_url is not None:
        # 只接受我们 own 的 /static/avatars/ 路径，避免被注入外链
        if body.avatar_url and not body.avatar_url.startswith("/static/avatars/"):
            raise HTTPException(
                status_code=400,
                detail={"code": "VALIDATION", "message": "头像 URL 不合法"},
            )
        user.avatar_url = body.avatar_url or None
        changed = True
    if body.mark_onboarded and user.onboarded_at is None:
        user.onboarded_at = datetime.now(tz=timezone.utc)
        changed = True
    if changed:
        await db.flush()
        await db.commit()
    return _user_response(user)


@router.post("/me/reroll-nickname", response_model=UserResponse)
async def reroll_nickname_endpoint(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """从 nickname 池里抽一个新名（排除当前），写回 user.nickname 并 cascade
    到 hepan_invites.a_nickname。Onboarding modal "↻ 换一个" 按钮调它。"""
    from app.services.nickname_pool import random_nickname
    new_nick = random_nickname(exclude=user.nickname)
    user.nickname = new_nick
    await db.execute(
        update(HepanInvite)
        .where(
            HepanInvite.user_id == user.id,
            HepanInvite.deleted_at.is_(None),
        )
        .values(a_nickname=new_nick)
    )
    await db.flush()
    await db.commit()
    return _user_response(user)


@router.post("/avatar", response_model=UserResponse)
async def upload_avatar_endpoint(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """上传头像 — 多媒体表单 ``file`` 字段，PNG/JPG/WebP/GIF。
    流程：读 → 校验大小 / mime → Pillow 解码 + 居中裁剪到 256×256
    → 编码为 WebP（约 80%） → 写到 ``server/var/avatars/<user>.webp``
    → 把 ``users.avatar_url`` 更新成 ``/static/avatars/<user>.webp``。
    返回更新后的 UserResponse。"""
    # 1. mime / extension whitelist
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION", "message": "请上传 PNG / JPG / WebP 图片"},
        )

    # 2. 读 + 大小限制（防止 bombs）
    raw = await file.read(_AVATAR_MAX_BYTES + 1)
    if len(raw) > _AVATAR_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION", "message": "图片不能超过 4MB"},
        )
    if not raw:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION", "message": "上传文件为空"},
        )

    # 3. Pillow 解码 + 居中正方形裁剪 + 缩到 256
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "INTERNAL", "message": "服务端缺少图片处理依赖"},
        ) from exc
    try:
        with Image.open(io.BytesIO(raw)) as img:
            # 自动按 EXIF 旋转，避免横竖错位
            img = ImageOps.exif_transpose(img)
            # 转 RGBA 再统一回 RGB（透明 → 白底），WebP 也支持透明但
            # 头像渲染都是圆形 mask，统一不透明输出最简单。
            if img.mode != "RGB":
                rgb = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode in ("RGBA", "LA"):
                    rgb.paste(img, mask=img.split()[-1])
                else:
                    rgb.paste(img.convert("RGB"))
                img = rgb
            # 居中正方形裁剪
            short = min(img.size)
            left = (img.width - short) // 2
            top = (img.height - short) // 2
            img = img.crop((left, top, left + short, top + short))
            img = img.resize((_AVATAR_OUTPUT_SIZE, _AVATAR_OUTPUT_SIZE), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="WEBP", quality=82, method=6)
            blob = buf.getvalue()
    except Exception as exc:  # noqa: BLE001 — Pillow can throw a wide variety
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION", "message": "图片解析失败，请换一张试试"},
        ) from exc

    # 4. 写盘 — 文件名带随机后缀，旧 URL 还能被旧 page-load 引用一会儿，
    # 浏览器自然清理；保留 user_id 前缀方便排查。
    _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(4)
    filename = f"{user.id}-{nonce}.webp"
    out_path = _AVATAR_DIR / filename
    out_path.write_bytes(blob)
    public_url = f"/static/avatars/{filename}"

    # 5. 顺手把旧文件删掉（如果是我们 own 的；外链不动）
    if user.avatar_url and user.avatar_url.startswith("/static/avatars/"):
        old_name = user.avatar_url.split("/")[-1]
        old_path = _AVATAR_DIR / old_name
        if old_path != out_path:
            try:
                old_path.unlink(missing_ok=True)
            except OSError:
                pass

    user.avatar_url = public_url
    await db.flush()
    await db.commit()
    return _user_response(user)


@router.delete("/account", response_model=AccountDeleteResponse)
async def delete_account_endpoint(
    body: AccountDeleteRequest,
    response: Response,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AccountDeleteResponse:
    # `confirm` is typed Literal["DELETE MY ACCOUNT"] in the schema, so pydantic
    # already rejects any other value at the schema layer.
    shredded_at = await auth_service.shred_account(db, user)
    _clear_session_cookie(response)
    return AccountDeleteResponse(shredded_at=shredded_at)
