"""Hepan (合盘) API. Mostly public — mirrors card.py's anonymous flow.

Flow:
  POST /api/hepan/invite                — A creates an invitation
                                          (optional_user：登录态会绑 user_id 到这条邀请)
  POST /api/hepan/{slug}/complete       — B opens link + submits their birth
  GET  /api/hepan/{slug}                — read current state (pending or completed)
  GET  /api/hepan/mine                  — list invites I've created (auth required)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.auth.deps import check_quota, current_user, optional_user, public_optional_user
from app.core.crypto import decrypt_dek
from app.core.db import get_db
from app.db_types import user_dek_context
from app.models.hepan_invite import HepanInvite
from app.models.hepan_message import HepanMessage
from app.models.user import User
from app.schemas.chart import BirthInput as ChartBirthInput
from app.schemas.hepan import (
    HepanChatMessageItem,
    HepanChatMessageRequest,
    HepanChatMessagesResponse,
    HepanCompleteRequest,
    HepanInviteRequest,
    HepanInviteResponse,
    HepanMineItem,
    HepanMineResponse,
    HepanResponse,
)
from app.services.card.loader import TYPES, load_all as load_card_data
from app.services.card.payload import build_card_payload
from app.services.card.slug import birth_hash
from app.services import paipan_adapter
from app.services.exceptions import PlanUpgradeRequiredError, ServiceError
from app.services.hepan.chat import list_messages as hepan_list_messages, stream_chat
from app.services.hepan.llm import stream_reading
from app.services.hepan.loader import find_pair, load_all as load_hepan_data
from app.services.hepan.payload import (
    _blend_hex,                      # 复用：列表项要返回 pair_theme_color
    build_completed_payload,
    build_pending_payload,
)
from app.services.hepan.slug import generate_slug
from app.services.quota import QuotaTicket

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _http_error(err: ServiceError) -> HTTPException:
    return HTTPException(status_code=err.status, detail=err.to_dict())

router = APIRouter(prefix="/api/hepan", tags=["hepan"])


def _ensure_data_loaded() -> None:
    """Belt-and-braces: data is already eagerly loaded at module import time,
    but this stays robust if someone reloads modules in tests."""
    load_card_data()
    load_hepan_data()


def _chart_birth_from_hepan_birth(birth) -> tuple[ChartBirthInput, bool]:
    """Convert flexible hepan birth input into the full chart birth schema.

    Hepan share links historically asked only for 年/月/日/时. Main chat context
    needs a paipan snapshot, whose schema requires gender. When gender is absent
    we compute with male as a technical fallback but mark it as not provided so
    prompts do not present gender-sensitive claims as certain.
    """
    data = birth.model_dump()
    gender_provided = data.get("gender") in {"male", "female"}

    city = data.get("city")
    if city:
        resolved = paipan_adapter.resolve_city(city)
        if resolved is not None:
            city = resolved["canonical"]

    chart_birth = ChartBirthInput(
        year=data["year"],
        month=data["month"],
        day=data["day"],
        hour=data["hour"],
        minute=data.get("minute", 0),
        city=city,
        longitude=data.get("longitude"),
        gender=data.get("gender") or "male",
        ziConvention=data.get("ziConvention") or "early",
        useTrueSolarTime=bool(data.get("useTrueSolarTime", True)),
    )
    return chart_birth, gender_provided


def _build_context_snapshot(birth) -> tuple[dict, dict]:
    """Build encrypted hepan context snapshot from a hepan birth input."""
    chart_birth, gender_provided = _chart_birth_from_hepan_birth(birth)
    paipan, warnings, engine_version = paipan_adapter.run_paipan(chart_birth)
    birth_snapshot = chart_birth.model_dump()
    birth_snapshot["genderProvided"] = gender_provided
    paipan["birthInput"] = birth_snapshot
    paipan["engineVersion"] = engine_version
    if warnings:
        paipan["warnings"] = warnings
    if gender_provided:
        paipan["gender"] = chart_birth.gender
    else:
        paipan["gender"] = "unknown"
        notes = paipan.get("contextNotes") if isinstance(paipan.get("contextNotes"), list) else []
        paipan["contextNotes"] = [
            *notes,
            "性别未提供；排盘以男命作技术占位，涉及大运顺逆、配偶星或性别敏感判断时必须先说明不确定。",
        ]
    return birth_snapshot, paipan


@router.post("/invite", response_model=HepanInviteResponse)
async def post_invite(
    req: HepanInviteRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> HepanInviteResponse:
    """A creates an invitation. Persists A's snapshot only (no birthdate).

    optional_user：登录态时绑 user_id 到 invite 行；匿名调用（老的分享卡链路 /
    没登录就发起的合盘）user_id 留 NULL，行为不变。"""
    _ensure_data_loaded()

    # Reuse the personal-card payload to derive type_id / state / day_stem.
    a_card = build_card_payload(req.birth, req.nickname)

    slug = generate_slug()
    row = HepanInvite(
        slug=slug,
        a_birth_hash=birth_hash(
            req.birth.year, req.birth.month, req.birth.day,
            req.birth.hour, req.birth.minute,
        ),
        a_type_id=a_card.type_id,
        a_state=a_card.state,
        a_day_stem=a_card.day_stem,
        a_nickname=a_card.nickname,
        status="pending",
        user_id=user.id if user is not None else None,
    )
    if user is not None:
        row.a_birth_input, row.a_paipan = _build_context_snapshot(req.birth)
    db.add(row)
    if user is not None:
        # FastAPI tears down yield dependencies after route return; explicit flush
        # keeps EncryptedJSONB binding inside the mounted creator DEK context.
        await db.flush()

    pending = build_pending_payload(
        slug=slug,
        a_type_id=a_card.type_id,
        a_state=a_card.state,
        a_day_stem=a_card.day_stem,
        a_nickname=a_card.nickname,
    )
    return HepanInviteResponse(
        slug=slug,
        a=pending.a,
        invite_url=f"/hepan/{slug}",
    )


@router.get("/mine", response_model=HepanMineResponse)
async def get_mine(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> HepanMineResponse:
    """登录用户创建过的合盘列表。最近创建在前。软删的不返。

    每行只回轻量元数据 — 列表 UI 不展开完整解读 / 角色对照，进 detail
    页（``GET /api/hepan/{slug}``）才有完整 HepanResponse。
    ``has_reading`` 标记是否已经生成过完整解读，让 mine 列表 / 弹窗历史
    都能给出"已读" 标记。"""
    _ensure_data_loaded()

    # A side avatar JOINed live from users.avatar_url — never snapshotted on the
    # invite row, so renames / new uploads reflect immediately. user_id is
    # always == user.id here (WHERE clause), but we keep the LEFT JOIN explicit
    # so the SELECT shape is obvious. B side has no b_user_id column → no JOIN
    # possible, b_avatar_url stays None until schema gains the FK.
    stmt = (
        select(HepanInvite, User.avatar_url.label("a_avatar_url"))
        .outerjoin(User, HepanInvite.user_id == User.id)
        .where(
            HepanInvite.user_id == user.id,
            HepanInvite.deleted_at.is_(None),
        )
        .order_by(desc(HepanInvite.created_at))
        .limit(200)
    )
    raw_rows = (await db.execute(stmt)).all()
    rows = [r[0] for r in raw_rows]
    avatar_by_slug: dict[str, Optional[str]] = {r[0].slug: r[1] for r in raw_rows}

    # 一次查所有 slug 的消息计数 — 比每行单独 COUNT 省 N 个 round-trip。
    # GROUP BY 后转 dict 给下面 lookup。空列表时 SQL 走 IN ()，PG 直接零行。
    slugs = [r.slug for r in rows]
    counts: dict[str, int] = {}
    if slugs:
        rows_count = (await db.execute(
            select(HepanMessage.hepan_slug, func.count(HepanMessage.id))
            .where(HepanMessage.hepan_slug.in_(slugs))
            .group_by(HepanMessage.hepan_slug)
        )).all()
        counts = {r[0]: int(r[1]) for r in rows_count}

    items: list[HepanMineItem] = []
    for r in rows:
        a_info = TYPES.get(r.a_type_id) or {}
        b_info = TYPES.get(r.b_type_id) if r.b_type_id else None
        category: str | None = None
        label: str | None = None
        pair_theme: str | None = None
        if r.status == "completed" and r.b_day_stem:
            pair, swapped = find_pair(r.a_day_stem, r.b_day_stem)
            category = pair["category"]
            label = pair["label"]
            if a_info and b_info:
                pair_theme = _blend_hex(a_info["theme_color"], b_info["theme_color"])
        items.append(HepanMineItem(
            slug=r.slug,
            status=r.status,                       # type: ignore[arg-type]
            a_nickname=r.a_nickname,
            b_nickname=r.b_nickname,
            a_cosmic_name=a_info.get("cosmic_name", ""),
            b_cosmic_name=(b_info or {}).get("cosmic_name") if b_info else None,
            category=category,
            label=label,
            pair_theme_color=pair_theme,
            a_avatar_url=avatar_by_slug.get(r.slug),
            # B side has no FK back to users today — always None.
            b_avatar_url=None,
            created_at=r.created_at,
            completed_at=r.completed_at,
            share_count=r.share_count,
            has_reading=bool(r.reading_generated_at),
            message_count=counts.get(r.slug, 0),
        ))
    return HepanMineResponse(items=items)


@router.delete("/{slug}", status_code=204)
async def delete_invite(
    slug: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """软删邀请。只有创建者本人能删；其他用户撞 404 (跟"不存在"同应答防枚举)。
    deleted_at 之后所有公共读取端点都 404，老链接立刻失效。"""
    row = (await db.execute(
        select(HepanInvite).where(
            HepanInvite.slug == slug,
            HepanInvite.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="invite not found")
    row.deleted_at = datetime.now(timezone.utc)
    return None


@router.post("/{slug}/complete", response_model=HepanResponse)
async def post_complete(
    slug: str,
    req: HepanCompleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(public_optional_user),
) -> HepanResponse:
    """B submits their birth → fills in the row → returns the full reading.
    软删的 invite 跟"不存在"同 404，B 这边链接立刻失效。"""
    _ensure_data_loaded()

    row = (await db.execute(
        select(HepanInvite).where(
            HepanInvite.slug == slug,
            HepanInvite.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="invite not found")

    if row.status == "completed":
        # Idempotent: re-completing returns the existing reading
        response = _row_to_response(row)
        response.is_creator = bool(user is not None and row.user_id == user.id)
        return response

    b_card = build_card_payload(req.birth, req.nickname)

    row.b_birth_hash = birth_hash(
        req.birth.year, req.birth.month, req.birth.day,
        req.birth.hour, req.birth.minute,
    )
    row.b_type_id = b_card.type_id
    row.b_state = b_card.state
    row.b_day_stem = b_card.day_stem
    row.b_nickname = b_card.nickname
    row.status = "completed"
    row.completed_at = datetime.now(timezone.utc)

    if row.user_id is not None:
        owner = await db.get(User, row.user_id)
        if owner is not None and owner.dek_ciphertext is not None:
            dek = decrypt_dek(owner.dek_ciphertext, request.app.state.kek)
            with user_dek_context(dek):
                row.b_birth_input, row.b_paipan = _build_context_snapshot(req.birth)
                await db.flush()

    response = _row_to_response(row)
    response.is_creator = bool(user is not None and row.user_id == user.id)
    return response


@router.get("/{slug}", response_model=HepanResponse)
async def get_hepan(
    slug: str,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(public_optional_user),
) -> HepanResponse:
    _ensure_data_loaded()

    # JOIN users.avatar_url onto the invite so the response carries A's live
    # avatar (B side has no FK → always None).
    raw = (await db.execute(
        select(HepanInvite, User.avatar_url.label("a_avatar_url"))
        .outerjoin(User, HepanInvite.user_id == User.id)
        .where(
            HepanInvite.slug == slug,
            HepanInvite.deleted_at.is_(None),
        )
    )).first()
    if raw is None:
        raise HTTPException(status_code=404, detail="invite not found")
    row, a_avatar_url = raw

    row.share_count += 1
    response = _row_to_response(row)
    response.a.avatar_url = a_avatar_url
    if response.b is not None:
        response.b.avatar_url = None
    response.is_creator = bool(user is not None and row.user_id == user.id)
    return response


@router.post("/{slug}/reading")
async def post_reading(
    slug: str,
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """SSE 流式生成完整解读（500-900 字）。

    Plan 5+ 计费：
      · lite     → 直接 402 PLAN_UPGRADE_REQUIRED，前端 paywall toast
      · standard → 走 chat_message 配额（150/天）
      · pro      → 同上但 600/天，事实上不限

    缓存：reading_text + reading_version 命中时不消耗配额，replay_cached
    重放整段。force=true 时无视缓存重新生成（也消耗配额）。

    幂等保证：commit-before-done 模式 — race 超额时 emit error 而不是 done，
    cache 不写。
    """
    _ensure_data_loaded()

    # Creator-only gate FIRST — non-creator B gets 404 (no information leak),
    # not a plan-upgrade hint. Mirrors the chat endpoint's behavior.
    row = await _load_creator_invite(db, slug, user)

    if user.plan == "lite":
        raise _http_error(PlanUpgradeRequiredError(
            feature="合盘完整解读", required_plan="standard",
        ))

    if row.status != "completed" or not row.b_day_stem:
        raise HTTPException(status_code=409, detail={
            "code": "HEPAN_NOT_COMPLETED",
            "message": "对方还没填生日，等 TA 完成后再读完整解读。",
        })

    # 缓存命中分支：不发配额 ticket，直接 replay。让缓存重读永远免费。
    expected_version_match = (
        row.reading_text
        and row.reading_version
        and not force
    )
    ticket: QuotaTicket | None = None
    if not expected_version_match:
        # 需要走 LLM —— 先预检 chat_message 配额
        check_dep = check_quota("chat_message")
        ticket = await check_dep(user=user, db=db)

    async def _gen():
        async for raw in stream_reading(
            db, user, row, force=force, ticket=ticket,
        ):
            yield raw
        await db.commit()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


# ── Multi-turn chat ─────────────────────────────────────────────────────


async def _load_creator_invite(
    db: AsyncSession, slug: str, user: User,
) -> HepanInvite:
    """合盘对话/解读只允许创建者本人。其他登录用户 / 不存在 / 已删 → 都 404。

    ``user_id`` 限制写在 WHERE 子句里（不是 row 拿出来再 check）—— 否则
    ORM 在解析 row 时会 trigger ``reading_text`` 的解密 (EncryptedText
    process_result_value)，B 的 DEK 解 A 的密文 → InvalidTag → 500，掩盖
    了我们想要的 404 语义。SQL 层先过滤掉非自己的 row，根本不让解密发生。

    显式 ``undefer(reading_text)`` — 那列默认是 deferred (避免无 DEK 的公共
    端点解密)，但 chat / reading 后续要在 SSE 生成器里读它，那时已经出了
    greenlet 友好上下文，lazy SELECT 会 MissingGreenlet。这里同步拉上。
    """
    row = (await db.execute(
        select(HepanInvite)
        .options(undefer(HepanInvite.reading_text))
        .where(
            HepanInvite.slug == slug,
            HepanInvite.deleted_at.is_(None),
            HepanInvite.user_id == user.id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="invite not found")
    return row


@router.get("/{slug}/messages", response_model=HepanChatMessagesResponse)
async def get_messages(
    slug: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> HepanChatMessagesResponse:
    """合盘对话历史 — 只创建者本人能拉。"""
    row = await _load_creator_invite(db, slug, user)
    msgs = await hepan_list_messages(db, row.slug)
    return HepanChatMessagesResponse(items=[
        HepanChatMessageItem(
            id=str(m.id),
            role=m.role,                       # type: ignore[arg-type]
            content=m.content or "",
            created_at=m.created_at,
        )
        for m in msgs
    ])


@router.post("/{slug}/messages")
async def post_message(
    slug: str,
    body: HepanChatMessageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    """合盘多轮对话 — SSE。Plan 5+ 付费功能：lite 直接 402。"""
    # Creator-only gate FIRST — non-creator B (any plan) gets 404, not a
    # 402 plan-upgrade hint. Mirrors post_reading's gate ordering.
    row = await _load_creator_invite(db, slug, user)

    if user.plan == "lite":
        raise _http_error(PlanUpgradeRequiredError(
            feature="合盘对话", required_plan="standard",
        ))

    if row.status != "completed" or not row.b_day_stem:
        raise HTTPException(status_code=409, detail={
            "code": "HEPAN_NOT_COMPLETED",
            "message": "对方还没填生日，等 TA 完成后再开始对话。",
        })

    check_dep = check_quota("chat_message")
    ticket: QuotaTicket = await check_dep(user=user, db=db)

    async def _gen():
        async for raw in stream_chat(
            db, user, row, body.message, ticket=ticket,
        ):
            yield raw
        await db.commit()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


def _row_to_response(row: HepanInvite) -> HepanResponse:
    """Compose HepanResponse from a DB row, dispatching on status."""
    if row.status == "completed" and row.b_type_id and row.b_state and row.b_day_stem:
        return build_completed_payload(
            slug=row.slug,
            a_type_id=row.a_type_id, a_state=row.a_state,
            a_day_stem=row.a_day_stem, a_nickname=row.a_nickname,
            b_type_id=row.b_type_id, b_state=row.b_state,
            b_day_stem=row.b_day_stem, b_nickname=row.b_nickname,
        )
    return build_pending_payload(
        slug=row.slug,
        a_type_id=row.a_type_id,
        a_state=row.a_state,
        a_day_stem=row.a_day_stem,
        a_nickname=row.a_nickname,
    )
