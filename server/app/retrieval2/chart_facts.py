"""Authoritative ten-god / 透藏 / 干合 fact sheet for chart-aware LLM prompts.

The polisher and selector LLMs both need this: without an explicit fact
table, they fall back to recall and routinely mislabel ten-gods (calling
甲日丁火 "食神" when it is actually 伤官) or ignore合化 relations the
backend already computes. Both call sites pin the table into the prompt
verbatim so the model can't override it.
"""
from __future__ import annotations

from typing import Any

PILLAR_LABELS: tuple[tuple[str, str], ...] = (
    ("年", "year"), ("月", "month"), ("日", "day"), ("时", "hour"),
)


def ten_god_facts(chart: dict[str, Any]) -> list[str]:
    """Return a list of authoritative facts about the chart, ready to be
    joined into a prompt. Each line is self-contained so callers can
    truncate / rearrange without parsing.

    Empty list if the paipan engine isn't importable or rizhu is missing —
    prompt callers should fall back gracefully.
    """
    try:
        from paipan.shi_shen import get_shi_shen
    except Exception:  # noqa: BLE001 — keep callers resilient if engine missing
        return []

    p = chart.get("PAIPAN") or chart
    sizhu = p.get("sizhu") or {}
    rizhu = str(p.get("rizhu") or "")
    if not rizhu or len(rizhu) != 1:
        return []

    cang_gan = p.get("cangGan") or {}
    visible_stems: dict[str, list[str]] = {}
    for label, key in PILLAR_LABELS:
        pillar = str(sizhu.get(key) or "")
        if not pillar:
            continue
        visible_stems[pillar[0]] = visible_stems.get(pillar[0], []) + [label]

    def _safe_shi(gan: str) -> str | None:
        try:
            return get_shi_shen(rizhu, gan)
        except Exception:  # noqa: BLE001
            return None

    stem_lines: list[str] = []
    for label, key in PILLAR_LABELS:
        pillar = str(sizhu.get(key) or "")
        if not pillar:
            continue
        gan = pillar[0]
        if key == "day":
            stem_lines.append(f"{label}干 {gan}（日主）")
            continue
        sg = _safe_shi(gan)
        stem_lines.append(f"{label}干 {gan}={sg or '?'}")

    branch_lines: list[str] = []
    for label, key in PILLAR_LABELS:
        pillar = str(sizhu.get(key) or "")
        if len(pillar) < 2:
            continue
        zhi = pillar[1]
        cang_list = cang_gan.get(key) or []
        parts = []
        for c in cang_list:
            sg = _safe_shi(c)
            tou = "（透干）" if c in visible_stems and c != rizhu else "（藏不透）"
            parts.append(f"{c}={sg or '?'}{tou}")
        branch_lines.append(f"{label}支 {zhi}：{'，'.join(parts) if parts else '—'}")

    facts: list[str] = []
    if stem_lines:
        facts.append("天干十神：" + "、".join(stem_lines))
    if branch_lines:
        facts.append("地支藏干（标注是否透到天干）：\n  " + "\n  ".join(branch_lines))

    gan_he = p.get("ganHe") or {}
    he_all = gan_he.get("all") or []
    he_with_ri = gan_he.get("withRiZhu") or []
    he_lines: list[str] = []
    for h in he_all:
        a, b = h.get("a"), h.get("b")
        wuxing = h.get("wuxing") or h.get("hua") or ""
        kind = h.get("kind") or "合"
        if a and b:
            he_lines.append(f"{a}{b}{kind}{('化' + wuxing) if wuxing else ''}")
    for h in he_with_ri:
        other = h.get("other") or h.get("a")
        wuxing = h.get("wuxing") or ""
        if other:
            he_lines.append(f"日主{rizhu}与{other}相合{('化' + wuxing) if wuxing else ''}")
    if he_lines:
        facts.append("干合关系：" + "；".join(he_lines))

    yongshen = str(p.get("yongshen") or "").strip()
    if yongshen:
        ys_gan = yongshen[0] if yongshen else ""
        ys_shi = _safe_shi(ys_gan) if ys_gan else None
        ys_visible = ys_gan in visible_stems
        ys_note = []
        if ys_shi:
            ys_note.append(f"十神身份是「{ys_shi}」（不要写成其它十神）")
        ys_note.append("透干" if ys_visible else "藏支不透（需大运/流年引出方能显效）")
        facts.append(f"用神 {yongshen}：" + "；".join(ys_note))

    return facts


__all__ = ["PILLAR_LABELS", "ten_god_facts"]
