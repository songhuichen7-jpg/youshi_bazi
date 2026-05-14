"""compact_chart_context: paipan 完整对象 → LLM 友好结构化上下文.

⚠️ 脱敏版本。完整版 ~415 行，负责把 ``paipan.compute()`` 输出的命盘完整对象压缩成 LLM
prompt 可直接拼装的结构化字段串：
- 四柱（年/月/日/时干支 + 藏干 + 十神）
- 十神力量评分 + 主导/失衡标记
- 格局识别结果
- 用神（调候 / 格局 / 扶抑 三法结果）
- 当前大运 + 下一步大运 + 当年/下一年流年
- 行运 5-bin 评分 + 关键机制标签

设计目标：在保留所有真实计算结果字段名的前提下，token 友好（一份命盘从 4-8k 压到 1-2k）。

完整版可面试时演示。
"""
from __future__ import annotations

from typing import Any


def compact_chart_context(chart: dict[str, Any] | None) -> str:
    """Compact paipan output into a token-friendly prompt block."""
    if not chart:
        return ""
    return "[REDACTED chart context — 见 docs/ARCHITECTURE.md]"
