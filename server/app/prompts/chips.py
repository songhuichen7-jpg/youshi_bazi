"""每轮回答后自动生成 3 个追问引导 chip（用 fast LLM tier）.

⚠️ 脱敏版本。完整版约 95 行，根据上一轮 assistant 回答生成 3 个用户可能感兴趣的追问短句。
"""
from __future__ import annotations
from typing import Any


def build_chips_messages(*, last_reply: str, **_extra: Any) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "[REDACTED chips prompt]"},
        {"role": "user", "content": last_reply[:200]},
    ]
