"""流年解读：某一年的流年对命主在当前大运背景下的作用.

⚠️ 脱敏版本。完整版约 120 行，含合冲刑害判定 + 节奏标签 + 输出格式约束。
"""
from __future__ import annotations
from typing import Any


def build_liunian_messages(
    *, paipan: dict[str, Any], year: int, **_extra: Any,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "[REDACTED liunian prompt]"},
        {"role": "user", "content": "[REDACTED]"},
    ]
