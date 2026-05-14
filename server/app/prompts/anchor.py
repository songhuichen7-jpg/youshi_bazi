"""build_classical_anchor: 把 retrieval3/retrieval2 返回的 EvidenceCard 列表
拼装成 LLM 友好的"古籍证据"段落，含书名、卷次、原文截断、引用契约。

⚠️ 脱敏版本。完整版约 95 行，控制每个 evidence 的格式 / 截断长度 / 总长度上限 /
terse 模式（板块 / chat 不同截断策略）。
"""
from __future__ import annotations
from typing import Any, Iterable


PER_SOURCE_MAX = 2500
TOTAL_MAX = 6000


def build_classical_anchor(
    cards: Iterable[dict[str, Any]] | None, *, terse: bool = False,
) -> str:
    """Render evidence cards into prompt-ready classical-anchor block."""
    if not cards:
        return ""
    return "[REDACTED classical anchor — 见 docs/ARCHITECTURE.md §4.4]"
