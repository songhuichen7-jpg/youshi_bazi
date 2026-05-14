"""Hepan-aware context for the main chart chat.

主 chart 对话里 LLM 默认只看到当前命盘 + retrieval 段。如果用户跟 阿谷 / rzy
有过合盘，那些关系就 sit 在数据库里 — 但 chat 不知道。结果：用户问 "我跟
阿谷一起做事顺不顺" 时 LLM 只能回 "需要更多信息"。

这一层负责把用户最近的几条已完成合盘转成一行 system prompt 提示，让 LLM
"记得" 用户跟谁合过盘以及关系底色。Token 成本：每条 ~30 字，最多 5 条
~150 字 / 1000 token 远低于 chat history 本身的预算。

调用方在 conversation_chat.stream_message 里调一次，结果作为
``hepan_summary`` 参数传给 prompts.expert.build_messages。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.prompts.context import compact_chart_context
from app.models.hepan_invite import HepanInvite
from app.services.card.loader import TYPES
from app.services.hepan.loader import find_pair
from app.services.hepan.payload import build_completed_payload


def _extract_context_slug(client_context: dict | None) -> str:
    if not isinstance(client_context, dict):
        return ""
    direct = client_context.get("hepan_slug")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    hepan = client_context.get("hepan")
    if isinstance(hepan, dict):
        slug = hepan.get("slug")
        if isinstance(slug, str) and slug.strip():
            return slug.strip()
    return ""


def _indent_block(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line if line else line for line in text.splitlines())


def _gender_note(paipan: dict | None, side_label: str) -> str:
    if not isinstance(paipan, dict):
        return ""
    birth = paipan.get("birthInput") if isinstance(paipan.get("birthInput"), dict) else {}
    if birth.get("genderProvided") is False:
        return f"{side_label}性别未提供；涉及伴侣星、大运顺逆和性别敏感判断时不要硬判。"
    return ""


def _side_fallback(row: HepanInvite, *, side: str) -> str:
    if side == "a":
        info = TYPES.get(row.a_type_id) or {}
        return (
            f"{row.a_nickname or 'A'}：{info.get('cosmic_name', '?')}，"
            f"日主{row.a_day_stem}，状态{row.a_state}"
        )
    info = TYPES.get(row.b_type_id or "") or {}
    return (
        f"{row.b_nickname or 'B'}：{info.get('cosmic_name', '?')}，"
        f"日主{row.b_day_stem or '?'}，状态{row.b_state or '?'}"
    )


def render_hepan_detail_context(row: HepanInvite) -> str:
    """Render a selected hepan invite as rich system-prompt context."""
    if row.status != "completed" or not row.b_type_id or not row.b_state or not row.b_day_stem:
        return ""

    payload = build_completed_payload(
        slug=row.slug,
        a_type_id=row.a_type_id,
        a_state=row.a_state,
        a_day_stem=row.a_day_stem,
        a_nickname=row.a_nickname,
        b_type_id=row.b_type_id,
        b_state=row.b_state,
        b_day_stem=row.b_day_stem,
        b_nickname=row.b_nickname,
    )
    a_name = row.a_nickname or payload.a.cosmic_name or "A"
    b_name = row.b_nickname or payload.b.cosmic_name if payload.b else row.b_nickname or "B"

    lines = [
        "【当前合盘上下文】",
        "用户正在围绕这段合盘关系提问；回答时优先使用这里的双方信息，不要要求用户重复提供对方生日。",
        f"关系：{a_name} × {b_name} — {payload.label}（{payload.category}）",
        "合盘卡片："
        f"{payload.state_pair_label or ''}；{payload.description or ''}"
        + (f"；{payload.modifier}" if payload.modifier else ""),
        f"A方角色：{payload.a.role or '—'}；B方角色：{payload.b.role if payload.b else '—'}",
    ]

    notes = [
        _gender_note(row.a_paipan, "A方"),
        _gender_note(row.b_paipan, "B方"),
    ]
    notes = [item for item in notes if item]
    if notes:
        lines.append("注意：" + " ".join(notes))

    if isinstance(row.a_paipan, dict):
        lines.append("A方命盘：")
        lines.append(_indent_block(compact_chart_context(row.a_paipan)))
    else:
        lines.append("A方命盘：" + _side_fallback(row, side="a"))

    if isinstance(row.b_paipan, dict):
        lines.append("B方命盘：")
        lines.append(_indent_block(compact_chart_context(row.b_paipan)))
    else:
        lines.append("B方命盘：" + _side_fallback(row, side="b"))

    return "\n".join(lines)


async def _selected_hepan_context_by_slug(
    db: AsyncSession, user_id: UUID, slug: str,
) -> str:
    if not slug:
        return ""
    row = (await db.execute(
        select(HepanInvite)
        .options(
            undefer(HepanInvite.a_birth_input),
            undefer(HepanInvite.a_paipan),
            undefer(HepanInvite.b_birth_input),
            undefer(HepanInvite.b_paipan),
        )
        .where(
            HepanInvite.slug == slug,
            HepanInvite.user_id == user_id,
            HepanInvite.deleted_at.is_(None),
            HepanInvite.status == "completed",
        )
    )).scalar_one_or_none()
    if row is None:
        return ""
    return render_hepan_detail_context(row)


async def selected_hepan_context_for_user(
    db: AsyncSession,
    user_id: UUID,
    client_context: dict | None,
) -> str:
    """Return rich context for the hepan slug selected by the main chat UI."""
    slug = _extract_context_slug(client_context)
    return await _selected_hepan_context_by_slug(db, user_id, slug)


async def hepan_context_for_user(
    db: AsyncSession,
    user_id: UUID,
    *,
    client_context: dict | None = None,
    conv_hepan_slug: str | None = None,
    limit: int = 5,
) -> str:
    """Prefer selected rich hepan detail; otherwise return recent summary.

    Resolution order for the "selected" slug:
      1. ``conv_hepan_slug`` — DB-authoritative (current preferred path)
      2. ``client_context.hepan.slug`` — legacy URL-param compat
    """
    selected = ""
    if conv_hepan_slug:
        selected = await _selected_hepan_context_by_slug(db, user_id, conv_hepan_slug)
    if not selected:
        selected = await selected_hepan_context_for_user(db, user_id, client_context)
    if selected:
        return selected
    return await recent_hepan_summaries_for_user(db, user_id, limit=limit)


async def recent_hepan_summaries_for_user(
    db: AsyncSession, user_id: UUID, *, limit: int = 5,
) -> str:
    """返回最多 ``limit`` 条已完成合盘的 system prompt 段落。

    没有任何已完成 invite → 返回空串（调用方 falsy check 跳过 inject）。
    每行格式：``跟 @{B 昵称}（{B cosmic_name}）— {label}（{category}）``。

    pending 的不算 — 用户可能邀请过但 B 没回，那段关系还没建立。软删的
    在 SQL where 里就过滤掉了，看不到。
    """
    rows = (await db.execute(
        select(HepanInvite)
        .where(
            HepanInvite.user_id == user_id,
            HepanInvite.deleted_at.is_(None),
            HepanInvite.status == "completed",
        )
        .order_by(desc(HepanInvite.created_at))
        .limit(limit)
    )).scalars().all()

    if not rows:
        return ""

    lines: list[str] = ["【你跟过谁合过盘（聊到相关话题可以参考）】"]
    for r in rows:
        if not r.b_day_stem or not r.b_type_id:
            # 已 completed 应该都有 b_day_stem，防御一下
            continue
        b_info = TYPES.get(r.b_type_id) or {}
        pair, _ = find_pair(r.a_day_stem, r.b_day_stem)
        b_name = r.b_nickname or "对方"
        b_cosmic = b_info.get("cosmic_name", "?")
        label = pair.get("label", "?")
        category = pair.get("category", "?")
        lines.append(f"- 跟 @{b_name}（{b_cosmic}）— {label}（{category}）")

    # 全靠 has-completed 行触发，但 for-loop 防御性 skip 了脏行；如果都被
    # skip 了，head + 0 行 — 直接 return 空串避免 "你跟过谁合过盘:\n" 孤悬。
    if len(lines) == 1:
        return ""
    return "\n".join(lines)
