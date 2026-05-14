"""七板块解读：性格 / 事业 / 财 / 感情 / 婚恋 / 健康 / 医疗.

⚠️ 脱敏版本。每个板块单独 LLM call，输出固定格式的板块卡。完整版约 140 行。
"""
from __future__ import annotations
from typing import Any, Optional

SECTION_IDS = ("personality", "career", "wealth", "love", "marriage", "health", "medical")


def build_section_messages(
    *, section_id: str, paipan: dict[str, Any], **_extra: Any,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": f"[REDACTED section prompt for {section_id}]"},
        {"role": "user", "content": "[REDACTED]"},
    ]
