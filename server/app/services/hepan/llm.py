"""Hepan 完整解读 — LLM stream + cache.

跟 chart_llm 同套机制，但 cache 不在 chart_cache（合盘没有 chart_id），
而是在 hepan_invites 行的 reading_text / reading_version / reading_generated_at
三列。版本号 = pairs/dynamics 的版本 + prompt 版本 → 16-char sha256 指纹，
prompt 改版后老 reading 自动失效，下次 GET reading 重新生成。

Plan 5+ 的付费功能：
  · lite        → 完全锁住，前端展示 paywall toast → /pricing
  · standard    → 走 chat_message quota（150/天），跟普通 chat 共池
  · pro         → 同上但 600/天，事实上不限
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import chat_stream_with_fallback
from app.llm.events import replay_cached, sse_pack
from app.llm.logs import insert_llm_usage_log
from app.models.hepan_invite import HepanInvite
from app.models.user import User
from app.services.card.loader import TYPES
from app.services.exceptions import UpstreamLLMError
from app.services.hepan.loader import DYNAMICS_VERSION, PAIRS_VERSION, find_pair
from app.services.hepan.mapping import (
    classify, state_pair_icon_key, state_pair_key,
)


# 改 prompt 必须 bump 这个 — 老 invite 上 reading_version 不再匹配，下次会
# 重新生成。这就是缓存失效的开关。
PROMPT_VERSION = "hepan-reading-v1-2026-05"


def _reading_version_for(invite: HepanInvite) -> str:
    """缓存失效信号：把 prompt 版本 + pairs/dynamics 版本拼起来再 sha256 取
    前 16 hex 字符（reading_version 列是 VARCHAR(40)）。任意一处变更指纹
    都不一样，老 reading 自然过期重生。invite 自身字段不进指纹 — 同一对
    人换状态 / 换昵称不需要重生（会被 row 内容缓存住，但状态影响 prompt
    的部分由 invite 的 a_state/b_state 决定，那两个字段一旦写入就不会再变）。
    """
    raw = f"{PROMPT_VERSION}|p={PAIRS_VERSION}|d={DYNAMICS_VERSION}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_messages(invite: HepanInvite) -> list[dict]:
    """组合两人的卡片 / pair 文案 / dynamic modifier 作为 LLM 上下文。

    输入只读 invite 行（已经在数据库里），不接触原始生日 — 隐私 posture
    跟 Card / 静态 hepan 卡片一致。"""
    a_info = TYPES.get(invite.a_type_id) or {}
    b_info = TYPES.get(invite.b_type_id) if invite.b_type_id else {}

    pair, swapped = find_pair(invite.a_day_stem, invite.b_day_stem or "")
    a_role = pair["b_role"] if swapped else pair["a_role"]
    b_role = pair["a_role"] if swapped else pair["b_role"]

    category, a_direction = classify(invite.a_day_stem, invite.b_day_stem or "")
    icon_key = state_pair_icon_key(invite.a_state, invite.b_state or "")
    state_pair = DYNAMICS_VERSION  # placeholder; we'll fetch label below
    from app.services.hepan.loader import DYNAMICS
    state_pair_label = DYNAMICS["state_pair_labels"][icon_key]
    modifier_key = state_pair_key(
        invite.a_state, invite.b_state or "", category, a_direction,
    )
    modifier = DYNAMICS["modifiers"][category].get(modifier_key) or ""

    a_name = invite.a_nickname or "A"
    b_name = invite.b_nickname or "B"

    system = (
        "你是「有时」的命理顾问，写命理解读像写散文 — 不算命，不预言时间。"
        "用克制、温和、有画面感的中文写。不要套语，不要「建议你...」这种工具感。"
        "全文 600-900 字。分成四段，每段一个明确小标题（用 # 一级标题），"
        "段落之间空一行。不要 bullet list。"
    )

    user_prompt = f"""
两个人，要不要成为长期的搭子，看的不是星座配不配，是底层的 五行节律 怎么交叉。
请基于下面的合盘数据写一份相处指南。

【A】{a_name}
- 类型: {a_info.get('cosmic_name', '?')}（日主 {invite.a_day_stem}）
- 状态: {invite.a_state}
- 在这段关系里的角色: {a_role}

【B】{b_name}
- 类型: {b_info.get('cosmic_name', '?')}（日主 {invite.b_day_stem}）
- 状态: {invite.b_state}
- 在这段关系里的角色: {b_role}

【关系底色】
- 类别: {category}
- 标签: {pair.get('label', '')} —— {' / '.join(pair.get('subtags', []))}
- 一句话感受: {pair.get('description', '')}
- 状态组合: {state_pair_label}
- 动态修饰: {modifier or '（暂无额外修饰）'}
- CTA: {pair.get('cta', '')}

请写四段，按这个结构：

# 你们的核心动力
～100-150 字。说清楚两个人在一起最甜 / 最有产出的那一面是什么。
不要重复"五行相生"这种术语，用具体的生活场景举例。

# 容易撞墙的地方
～180-220 字。描述最常见的两种摩擦场景。每种摩擦从 A / B 各自的视角分别说一句，
让两个人读到的时候都有"对，TA 这时候确实会这样"的感觉。

# 怎么相互调成最舒服的频率
～200-250 字。给 1-2 个具体可操作的建议，比如"周末让 A 决定行程，工作日让 B 主导"
之类。避免泛泛的"多沟通"。

# 一句话总结
～40-60 字。给这段关系一个画面感强的比喻收尾。
"""

    return [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": user_prompt.strip()},
    ]


async def stream_reading(
    db: AsyncSession,
    user: User,
    invite: HepanInvite,
    *,
    force: bool,
    ticket,                # QuotaTicket | None — 调用方做 quota 预检后传进来
) -> AsyncIterator[bytes]:
    """SSE generator. 复用 chart_llm 的 commit-before-done 模式。

    Cache 命中（reading_text 非空 + version 匹配 + 不 force）→ replay_cached，
    不消耗 LLM 也不扣配额。否则全程跑 LLM stream，commit 配额后写 cache。
    """
    expected_version = _reading_version_for(invite)
    if (
        not force
        and invite.reading_text
        and invite.reading_version == expected_version
    ):
        async for raw in replay_cached(invite.reading_text, "(cached)"):
            yield raw
        return

    messages = _build_messages(invite)
    accumulated = ""
    model_used: str | None = None
    prompt_tok = completion_tok = total_tok = 0
    t_start = time.monotonic()
    err: UpstreamLLMError | None = None

    try:
        async for ev in chat_stream_with_fallback(
            messages=messages, tier="primary",
            temperature=0.7, max_tokens=2400,
            first_delta_timeout_ms=0,
        ):
            if ev["type"] == "model":
                model_used = ev["modelUsed"]
                yield sse_pack(ev)
            elif ev["type"] == "delta":
                accumulated += ev["text"]
                yield sse_pack(ev)
            elif ev["type"] == "done":
                prompt_tok = ev.get("prompt_tokens", 0)
                completion_tok = ev.get("completion_tokens", 0)
                total_tok = ev.get("tokens_used", 0)
    except UpstreamLLMError as e:
        err = e
        yield sse_pack({"type": "error", "code": e.code, "message": e.message})

    duration_ms = int((time.monotonic() - t_start) * 1000)

    if err is not None:
        await insert_llm_usage_log(
            db, user_id=user.id, chart_id=None,
            endpoint="hepan_reading", model=model_used,
            prompt_tokens=None, completion_tokens=None,
            duration_ms=duration_ms, error=f"{err.code}: {err.message}",
        )
        return

    # Commit-before-done — 跟 chart_llm 同节奏：先 commit 配额，
    # race-超出限额时 emit error 而不是 done，cache 不写。
    if ticket is not None:
        try:
            await ticket.commit()
        except Exception as e:  # noqa: BLE001
            yield sse_pack({"type": "error", "code": "QUOTA_EXCEEDED", "message": str(e)})
            await insert_llm_usage_log(
                db, user_id=user.id, chart_id=None,
                endpoint="hepan_reading", model=model_used,
                prompt_tokens=None, completion_tokens=None,
                duration_ms=duration_ms, error=f"QUOTA_EXCEEDED: {e}",
            )
            return

    invite.reading_text = accumulated
    invite.reading_version = expected_version
    invite.reading_generated_at = datetime.now(tz=timezone.utc)
    await db.flush()

    await insert_llm_usage_log(
        db, user_id=user.id, chart_id=None,
        endpoint="hepan_reading", model=model_used,
        prompt_tokens=prompt_tok, completion_tokens=completion_tok,
        duration_ms=duration_ms,
    )
    yield sse_pack({
        "type": "done",
        "full": accumulated,
        "tokens_used": total_tok,
    })
