"""Stage 1 router: intent classifier with LLM + keyword fallback.

⚠️ 脱敏版本。完整版 ~380 行包含：

1. ``INTENTS``：15 类意图标签。
2. ``PRIORITY``：keyword fallback 命中优先级。
3. ``KEYWORDS``：每个 intent 的关键词字典（这是 IP 核心之一）。
4. ``build_router_messages(...)``：组装 router LLM 的 messages，约束 JSON schema 输出：
       {"intent": "...", "reason": "...", "retrieval_focus": "...",
        "artifact": null | "song"/"movie"/"flower",
        "answer_plan": {"format": "...", "style": "...", "should_clarify": bool}}
5. ``parse_router_json(...)``：LLM 输出 → 结构化路由结果，含 json 修复与降级。
6. ``classify_by_keywords(...)``：LLM 失败时按 PRIORITY 顺序查 KEYWORDS。

完整版可面试时演示。
"""
from __future__ import annotations

from typing import Any, Optional

INTENTS: list[str] = [
    "relationship", "career", "wealth", "timing",
    "personality", "health", "meta", "chitchat", "other",
    "dayun_step", "liunian", "appearance", "special_geju",
    "divination", "media",
]

PRIORITY: list[str] = [
    "divination", "timing", "relationship", "appearance",
    "career", "wealth", "media", "health", "special_geju",
    "meta", "personality", "chitchat",
]

KEYWORDS: dict[str, list[str]] = {intent: [] for intent in INTENTS}
# 完整版：每个 intent 配 8-20 个中文关键词


def build_router_messages(
    *, paipan: dict[str, Any], user_message: str,
    history: Optional[list[dict[str, str]]] = None, **_extra: Any,
) -> list[dict[str, str]]:
    """Build router LLM messages with JSON schema constraint."""
    return [
        {"role": "system", "content": "[REDACTED router system prompt]"},
        *(history or []),
        {"role": "user", "content": user_message},
    ]


def parse_router_json(raw: str) -> dict[str, Any]:
    """Parse + sanitize router LLM output. Returns intent_info dict."""
    return {"intent": "other", "reason": "redacted", "source": "stub"}


def classify_by_keywords(user_message: str) -> dict[str, Any]:
    """Keyword fallback when LLM router fails."""
    return {"intent": "other", "reason": "keyword fallback", "source": "keyword"}
