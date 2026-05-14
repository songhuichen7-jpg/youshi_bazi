"""Generic section parser shared by family extractors.

Extracts (## heading, body_text, char_offsets) tuples from a markdown file.
Skips frontmatter and metadata lines. Body is everything between this `##`
heading and the next one (or EOF).

Used by: shensha / geju / liuqin / appearance / concept extractors.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_HEADING_RE = re.compile(r"^(#+)\s+(.*?)\s*$")
_META_PREFIX_RE = re.compile(r"^(来源|作者|原著|编者|评注|译者|出处)[:：]")


@dataclass(frozen=True, slots=True)
class Section:
    level: int
    heading: str
    body: str
    char_start: int
    char_end: int


def parse_sections(raw: str, *, min_level: int = 2, max_level: int = 6) -> list[Section]:
    """Walk a markdown blob, return all `##`+ sections with their body text."""
    lines = raw.splitlines(keepends=True)
    out: list[Section] = []

    cur_level: int | None = None
    cur_heading: str = ""
    cur_start: int = 0
    cur_buf: list[str] = []

    cursor = 0

    def flush(end: int) -> None:
        nonlocal cur_buf
        if cur_level is None:
            cur_buf = []
            return
        body_text = "".join(cur_buf).strip()
        # 去掉 frontmatter 元行
        body_lines = [
            ln for ln in body_text.splitlines()
            if not _META_PREFIX_RE.match(ln.strip())
        ]
        body_clean = "\n".join(body_lines).strip()
        out.append(Section(
            level=cur_level, heading=cur_heading, body=body_clean,
            char_start=cur_start, char_end=end,
        ))
        cur_buf = []

    for line in lines:
        line_no_nl = line.rstrip("\n")
        line_start = cursor
        cursor += len(line)

        m = _HEADING_RE.match(line_no_nl)
        if m and min_level <= len(m.group(1)) <= max_level:
            flush(line_start)
            cur_level = len(m.group(1))
            cur_heading = m.group(2).strip()
            cur_start = line_start
            continue

        if cur_level is not None:
            cur_buf.append(line)

    flush(cursor)
    return out


def section_index(path: Path) -> dict[str, Section]:
    """Map heading → first matching Section. Convenience for known-heading lookup."""
    raw = path.read_text(encoding="utf-8")
    out: dict[str, Section] = {}
    for s in parse_sections(raw):
        if s.heading not in out:
            out[s.heading] = s
    return out


__all__ = ["Section", "parse_sections", "section_index"]
