"""Markdown classics → ClaimUnit list.

Decisions:

* **Stable id**: ``<book>.<chapter-stem>.<paragraph-idx>[.<sentence-idx>]``.
  Re-running on unchanged source produces the same ids.
* **Section-aware**: most-recent ``##`` heading is recorded as the section.
* **Length policy**: ~50–220 chars per claim. Long paragraphs split at
  ``。！？；`` boundaries; sentences merged greedily into target band.
* **Coarse kind detection**: gan-zhi-chain paragraphs are flagged ``case``;
  meta lines (frontmatter, table rows, dividers) are skipped.
* **Per-book profile**: 穷通宝鉴 / 渊海子平 prefer paragraph-level units
  (poetic/骈句 cadence); other books sentence-split.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .normalize import normalize
from .types import ClaimKind, ClaimUnit

TARGET_MIN = 18
TARGET_MAX = 240
SENT_BREAK = re.compile(r"(?<=[。！？；])")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
HR_RE = re.compile(r"^\s*[-*_]{3,}\s*$")
META_PREFIX_RE = re.compile(r"^(来源|作者|原著|编者|评注|译者|出处)[:：]")
GANZHI_PAIR_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")
GANZHI_CHAIN_RE = re.compile(r"^(?:[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]){2,}$")
CASE_OPENERS = (
    "此造", "此命",
    *(f"如{g}" for g in "甲乙丙丁戊己庚辛壬癸"),
    *(f"某{g}" for g in "甲乙丙丁戊己庚辛壬癸"),
)

# Splitter v2 (2026-05-08): chunk_type widening. Without these, 三命通会
# 卷十二的"必贫必夭"断语和子平真诠的"先观月令"原则在 retrieval 排序
# 中等权,LLM 会把绝对凶吉断语当成结构化原则照搬。
#
# 检测规则保守:必须组合两类信号才升格为 judgement / shensha,只有 absolutist
# 词就丢主结构是常见误判;所以同段如果还讨论制化 / 救应 / 月令 / 用神,
# 一律保留 principle.

# 极端凶吉断词:用"必/凶/夭/克/贫/绝/破"等绝对词
JUDGEMENT_HARD_TERMS = (
    "必贫", "必贱", "必夭", "必凶", "必破", "必绝",
    "贫夭", "夭折", "凶夭", "克妻", "克夫", "克子",
    "为祸", "刑伤", "孤穷", "贫穷",
)
# 救应词:出现这些字样意味着断语带条件 / 制化方法,信号仍然有用
JUDGEMENT_REMEDY_TERMS = (
    "得制", "得救", "化煞", "化杀", "制杀", "印化",
    "反成", "反吉", "反贵", "见印", "见食",
    "得宜", "配合得", "若有", "若得",
    "用神", "月令", "格局", "成格",
)

# 神煞名核心集 (歌诀 / 散布断语里最常见的). 把单一神煞名和多个神煞名连续
# 出现的段落都视为 shensha 候选;但若同段还涉及格局 / 用神 / 月令的结构
# 论述,则保留 principle (神煞被结构吸收成为辅助信号)
SHENSHA_TERMS = (
    "桃花", "驿马", "天乙", "天乙贵人", "贵人",
    "孤辰", "寡宿", "空亡", "华盖", "羊刃",
    "金舆", "禄神", "文昌", "学堂",
    "天罗", "地网", "六厄", "亡神", "劫煞",
)
SHENSHA_STRUCTURAL_TERMS = (
    "月令", "格局", "用神", "成格", "破格",
    "成败", "制化", "调候", "扶抑",
    "日主", "提纲",
)


def _has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(t in text for t in terms)


@dataclass(frozen=True, slots=True)
class BookProfile:
    key: str
    keep_full_paragraphs: bool = False
    """Do not sentence-split (preserves cadence in 渊海子平 / 穷通宝鉴)."""


_PROFILES: dict[str, BookProfile] = {
    "ditian-sui": BookProfile("ditian-sui"),
    "qiongtong-baojian": BookProfile("qiongtong-baojian", keep_full_paragraphs=True),
    "sanming-tonghui": BookProfile("sanming-tonghui"),
    "yuanhai-ziping": BookProfile("yuanhai-ziping", keep_full_paragraphs=True),
    "ziping-zhenquan": BookProfile("ziping-zhenquan"),
}


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text[end + 4:].lstrip("\n") if end != -1 else text


def _clean_heading(line: str) -> str:
    m = HEADING_RE.match(line)
    if not m:
        return ""
    raw = m.group(2).strip()
    return re.sub(r"^[一二三四五六七八九十百\d]+[、.．]\s*", "", raw)


def _strip_inline(line: str) -> str:
    line = re.sub(r"^>\s*", "", line)
    return line.replace("**", "").replace("`", "").strip()


def _is_skippable(line: str) -> bool:
    if not line:
        return True
    if HR_RE.match(line) or TABLE_RE.match(line) or line.startswith("|"):
        return True
    return bool(META_PREFIX_RE.match(line))


def _detect_kind(text: str) -> ClaimKind:
    compact = re.sub(r"[\s　、，,；;。:：]+", "", text)
    if not compact:
        return "meta"
    if GANZHI_CHAIN_RE.fullmatch(compact):
        return "case"
    if compact.startswith(CASE_OPENERS):
        return "case"
    if len(compact) <= 18 and len(GANZHI_PAIR_RE.findall(compact)) >= 2:
        return "case"
    if re.match(r"^[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]日生", compact):
        return "case"
    if len(GANZHI_PAIR_RE.findall(compact)) >= 6 and any(
        m in compact for m in ("命", "运", "日生", "此造")
    ):
        return "case"

    # v2: judgement vs shensha vs principle
    has_judgement = _has_any(compact, JUDGEMENT_HARD_TERMS)
    has_remedy = _has_any(compact, JUDGEMENT_REMEDY_TERMS)
    if has_judgement and not has_remedy:
        return "judgement"

    has_shensha = _has_any(compact, SHENSHA_TERMS)
    has_struct = _has_any(compact, SHENSHA_STRUCTURAL_TERMS)
    # 纯神煞列举 (蛛网式 "桃花在子午..., 驿马居寅申...") 才降权;
    # 段里同时讨论格局 / 用神则结构论述吸收神煞,保留 principle.
    if has_shensha and not has_struct:
        return "shensha"

    return "principle" if len(compact) >= 18 else "heuristic"


def _sentence_chunks(paragraph: str, target_max: int = TARGET_MAX) -> list[str]:
    pieces = [p.strip() for p in SENT_BREAK.split(paragraph) if p.strip()]
    if not pieces:
        return []
    out: list[str] = []
    buf = ""
    for sent in pieces:
        if len(sent) > target_max:
            if buf:
                out.append(buf)
                buf = ""
            cursor = 0
            while cursor < len(sent):
                end = min(cursor + target_max, len(sent))
                if end < len(sent):
                    cut = sent.rfind("，", cursor, end)
                    if cut > cursor + target_max // 2:
                        end = cut + 1
                out.append(sent[cursor:end].strip())
                cursor = end
            continue
        if buf and len(buf) + len(sent) > target_max:
            out.append(buf)
            buf = sent
        else:
            buf += sent
    if buf:
        out.append(buf)
    return [s for s in out if len(s) >= 4]


def split_chapter(book: str, chapter_file: str, raw: str) -> list[ClaimUnit]:
    """Top-level: ``raw`` markdown -> ``ClaimUnit[]``."""
    profile = _PROFILES.get(book) or BookProfile(book)
    body = _strip_frontmatter(raw)
    chapter_title = ""
    section: str | None = None
    paragraphs: list[tuple[str | None, str]] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        line = " ".join(p.strip() for p in buf if p.strip())
        buf = []
        if line:
            paragraphs.append((section, normalize(line)))

    for raw_line in body.splitlines():
        m = HEADING_RE.match(raw_line.rstrip())
        if m:
            flush()
            level = len(m.group(1))
            heading = _clean_heading(raw_line)
            if not chapter_title and level <= 2:
                chapter_title = heading
            elif heading and heading != chapter_title:
                section = heading
            continue
        line = _strip_inline(raw_line)
        if _is_skippable(line):
            flush()
            continue
        if not line:
            flush()
            continue
        buf.append(line)
    flush()

    chapter_stem = Path(chapter_file).stem
    if not chapter_title:
        chapter_title = chapter_stem.replace("-", " ").replace("_", " ")

    out: list[ClaimUnit] = []
    for para_idx, (sec, paragraph) in enumerate(paragraphs):
        if not paragraph:
            continue
        if profile.keep_full_paragraphs and len(paragraph) <= TARGET_MAX * 1.5:
            chunks = [paragraph]
        else:
            chunks = _sentence_chunks(paragraph)
        if not chunks:
            continue
        if len(chunks) == 1:
            text = chunks[0]
            if len(text) >= TARGET_MIN:
                out.append(ClaimUnit(
                    id=f"{book}.{chapter_stem}.{para_idx:04d}",
                    book=book, chapter_file=chapter_file,
                    chapter_title=chapter_title, section=sec,
                    text=text, paragraph_idx=para_idx,
                    kind=_detect_kind(text),
                ))
            continue
        for sent_idx, text in enumerate(chunks):
            if len(text) < TARGET_MIN:
                continue
            out.append(ClaimUnit(
                id=f"{book}.{chapter_stem}.{para_idx:04d}.{sent_idx:02d}",
                book=book, chapter_file=chapter_file,
                chapter_title=chapter_title, section=sec,
                text=text, paragraph_idx=para_idx,
                kind=_detect_kind(text),
            ))
    return out


def iter_classics(classics_root: Path) -> Iterable[tuple[str, str]]:
    """Yield ``(rel_path, raw_text)`` for every chapter-file under
    ``classics/<book>/``. Skips index/readme files and unknown books."""
    for book_dir in sorted(p for p in classics_root.iterdir() if p.is_dir()):
        book = book_dir.name
        if book not in _PROFILES:
            continue
        for path in sorted(book_dir.rglob("*.md")):
            name = path.name
            if name.startswith("00_") or name == "FILENAME_MAP.md":
                continue
            yield path.relative_to(classics_root).as_posix(), path.read_text(encoding="utf-8")


__all__ = ["BookProfile", "split_chapter", "iter_classics"]
