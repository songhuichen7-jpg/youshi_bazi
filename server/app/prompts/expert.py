"""Stage 2 expert: intent-aware system prompt builder (主对话 expert prompt 组装器).

⚠️ 此文件为脱敏版本，保留架构与函数签名，省略具体提示词内容。

完整实现包含约 540 行：
- ``INTENT_GUIDE``：15 类意图（relationship / career / wealth / timing / personality /
  health / meta / chitchat / other / appearance / special_geju / liunian /
  dayun_step / divination / media）的强约束聚焦方向。
- ``FALLBACK_STYLE``：未匹配 shard 时的兜底输出风格。
- ``_load_shards_for(intent)``：始终加载 ``shards/core.md``，按 intent 追加
  ``shards/<intent>.md``。
- ``build_expert_messages(...)``：主组装器，把以下层拼成最终的 messages 数组：
    1. system role 身份
    2. ``style.py``：世界观 + 古籍引用契约 + 输出风格预设
    3. shards/core.md + shards/<intent>.md
    4. ``compact_chart_context(chart)``：命盘结构化字段
    5. ``build_classical_anchor(evidence_cards)``：retrieval3 注入的古籍真本
    6. ``INTENT_GUIDE[intent]``：本轮聚焦方向
    7. 时间锚（today_ymd / year_gz / month_gz）
    8. history messages（滑窗）
    9. 当前 user message

完整版可面试时演示。设计思路见 README / docs/ARCHITECTURE.md。
"""
from __future__ import annotations

from typing import Any, Optional

from app.prompts.anchor import build_classical_anchor
from app.prompts.context import compact_chart_context
from app.prompts.loader import load_shard
from app.prompts.style import (
    BAZI_OUTPUT_STYLE_PRESET,
    BAZI_WORLDVIEW,
    CLASSICAL_QUOTE_POLICY,
)


CLIENT_CONTEXT_MAX_CLASSICS = 6
CLIENT_CONTEXT_QUOTE_MAX = 240
CLIENT_CONTEXT_NOTE_MAX = 180


FALLBACK_STYLE = "[REDACTED — 见 docs/ARCHITECTURE.md 第 4.1 节描述]"


INTENT_GUIDE: dict[str, str] = {
    intent: f"[REDACTED — intent guide for {intent!r}]"
    for intent in (
        "relationship", "career", "wealth", "timing", "personality",
        "health", "meta", "chitchat", "other", "appearance",
        "special_geju", "liunian", "dayun_step",
    )
}


def _load_shards_for(intent: str) -> str:
    """Always include core shard; append intent-specific shard if exists."""
    out: list[str] = []
    core = load_shard("core")
    if core:
        out.append(core)
    if intent:
        specific = load_shard(intent)
        if specific:
            out.append(specific)
    return "\n\n---\n\n".join(out)


def _render_client_context(client_context: Optional[dict[str, Any]]) -> str:
    """Render client-provided classics excerpts (for chart-specific persona).

    完整版在此压缩 client_context 里的古籍片段到 prompt 友好的格式。
    """
    return ""


def build_expert_messages(
    *,
    paipan: dict[str, Any],
    user_message: str,
    intent: str,
    history: Optional[list[dict[str, str]]] = None,
    retrieved: Optional[list[dict[str, Any]]] = None,
    client_context: Optional[dict[str, Any]] = None,
    **_extra: Any,
) -> list[dict[str, str]]:
    """Build the final OpenAI-compatible messages list for the expert turn.

    完整版按下列顺序拼装 system content：
        BAZI_WORLDVIEW
        + BAZI_OUTPUT_STYLE_PRESET
        + CLASSICAL_QUOTE_POLICY
        + _load_shards_for(intent)
        + FALLBACK_STYLE (if no shard matched)
        + compact_chart_context(paipan)
        + _render_client_context(client_context)
        + build_classical_anchor(retrieved, terse=False)
        + INTENT_GUIDE[intent]
        + 时间锚 (today_ymd / year_gz / month_gz)
    然后 history + 当前 user_message。
    """
    system_content = "[REDACTED expert system prompt — 见 docs/ARCHITECTURE.md]"
    history_window = history or []
    return [
        {"role": "system", "content": system_content},
        *history_window,
        {"role": "user", "content": user_message},
    ]
