"""单步大运展开：分析某一步大运（干支 + 起运年龄）的十年走向.

⚠️ 脱敏版本。完整版约 115 行，按 paipan 计算出的大运结构 + 跨步互动结果生成 LLM messages。
"""
from __future__ import annotations
from typing import Any


def build_dayun_step_messages(
    *, paipan: dict[str, Any], step: dict[str, Any], **_extra: Any,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "[REDACTED dayun_step prompt]"},
        {"role": "user", "content": "[REDACTED]"},
    ]
