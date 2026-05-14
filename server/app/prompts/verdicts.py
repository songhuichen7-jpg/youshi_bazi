"""Verdict generator: 命局总论（一次性长文，非流式 turn）.

⚠️ 脱敏版本。完整版约 100 行，按用户命盘 + persona 生成命局开盘总论。
"""
from __future__ import annotations
from typing import Any


def build_verdict_messages(
    *, paipan: dict[str, Any], **_extra: Any,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "[REDACTED verdict prompt]"},
        {"role": "user", "content": "[REDACTED]"},
    ]
