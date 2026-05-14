"""梅花易数起卦：时间起卦 + 64 卦本卦原文 + 白话解.

⚠️ 脱敏版本。完整版约 70 行，含起卦算法 + 卦象解读 prompt。
"""
from __future__ import annotations
from typing import Any


def build_gua_messages(*, user_question: str, **_extra: Any) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "[REDACTED gua prompt]"},
        {"role": "user", "content": user_question},
    ]
