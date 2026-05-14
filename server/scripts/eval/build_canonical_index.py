"""Build canonical evidence index for the bazi retrieval eval framework.

Phase 1: pure programmatic extraction (no LLM calls).

Outputs ``server/var/eval/canonical_index.json`` with:
* QTBJ sections — 10 day stems × 12 months ≈ 120 (day_gan, month_zhi) units.
  Each unit aggregates the paragraphs in 穷通宝鉴 论X (干) that introduce
  themselves as "<月份>X" for that month.
* SMTH entries — 60 day pillars × 12 hour pillars = 720 (day_pillar,
  hour_pillar) units, one per row in 三命通会 卷八/卷九.

The eval set references these by ``canonical_key`` so that re-chunking,
re-tagging, or splitter changes do not invalidate ground truth.

Usage::

    PYTHONPATH=server uv run python -m scripts.eval.build_canonical_index
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

logger = logging.getLogger("eval.canonical_index")

REPO_ROOT = Path(__file__).resolve().parents[3]
CLASSICS_ROOT = REPO_ROOT / "classics"
OUT_PATH = REPO_ROOT / "server" / "var" / "eval" / "canonical_index.json"

GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
GAN_SET = set(GAN)
ZHI_SET = set(ZHI)

# 五鼠遁 — 由日干推子时干。其余时辰按 (zhi_idx) 顺序累加。
WU_SHU_DUN_FIRST_GAN = {
    "甲": "甲", "己": "甲",
    "乙": "丙", "庚": "丙",
    "丙": "戊", "辛": "戊",
    "丁": "庚", "壬": "庚",
    "戊": "壬", "癸": "壬",
}


def hour_pillar_for(day_gan: str, hour_zhi: str) -> str:
    first_gan = WU_SHU_DUN_FIRST_GAN[day_gan]
    zhi_idx = ZHI.index(hour_zhi)
    gan_idx = (GAN.index(first_gan) + zhi_idx) % 10
    return GAN[gan_idx] + hour_zhi


# ─────────────────────────────────────────────────────────────────────────────
# QTBJ — 穷通宝鉴
# ─────────────────────────────────────────────────────────────────────────────

QTBJ_FILE_TO_GAN = {
    "02_lun-jia-mu.md": "甲",
    "03_lun-yi-mu.md": "乙",
    "04_lun-bing-huo.md": "丙",
    "05_lun-ding-huo.md": "丁",
    "06_lun-wu-tu.md": "戊",
    "07_lun-ji-tu.md": "己",
    "08_lun-geng-jin.md": "庚",
    "09_lun-xin-jin.md": "辛",
    "10_lun-ren-shui.md": "壬",
    "11_lun-gui-shui.md": "癸",
}

QTBJ_GAN_TO_ELEMENT = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火",
    "戊": "土", "己": "土", "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# 月份名 → 月支
QTBJ_MONTH_NAME_TO_ZHI = {
    "正月": "寅", "一月": "寅",
    "二月": "卯",
    "三月": "辰",
    "四月": "巳",
    "五月": "午",
    "六月": "未",
    "七月": "申",
    "八月": "酉",
    "九月": "戌",
    "十月": "亥",
    "十一月": "子",
    "十二月": "丑", "腊月": "丑",
}

# 段首形如 "正月甲木" / "正二月甲木" / "五六月乙木" / "总之十二月甲木" / "凡三春甲木"
# 第一组捕获月份串(可多月), 第二组捕获 X (干) + 元素 (木/火/土/金/水)
QTBJ_MONTH_HEAD_RE = re.compile(
    r"^(?:总之|凡)?\s*"
    r"((?:正|一|二|三|四|五|六|七|八|九|十一|十二|十|腊)月)+"
    r"\s*(?:[甲乙丙丁戊己庚辛壬癸])(?:[木火土金水])"
)

# 月份切词 — 把 "正二月" / "五六月" 这种切成 ["正月", "二月"] / ["五月", "六月"]
QTBJ_MONTH_SPLIT_RE = re.compile(
    r"(正|一|二|三|四|五|六|七|八|九|十一|十二|十|腊)"
)


def _extract_qtbj_months(head: str) -> list[str]:
    """Given a paragraph leading fragment like "正二月" or "五六月" or "十二月",
    return all referenced month names. Returns [] when no month is found.
    """
    # 抓出"X月"前面的所有数字串。head 可能是 "正二月甲木..." → 取"正二月"
    # 用 MONTH_HEAD_RE 已经定位到段首，这里只解析"X月"前的数字串。
    match = re.match(
        r"^(?:总之|凡)?\s*((?:正|一|二|三|四|五|六|七|八|九|十一|十二|十|腊)+)月",
        head,
    )
    if not match:
        return []
    nums = match.group(1)
    months: list[str] = []
    # 要从右向左贪心匹配多字符数字（十一/十二）
    cursor = 0
    while cursor < len(nums):
        # 优先尝试两字
        if cursor + 2 <= len(nums) and nums[cursor:cursor + 2] in ("十一", "十二"):
            months.append(nums[cursor:cursor + 2] + "月")
            cursor += 2
        else:
            months.append(nums[cursor] + "月")
            cursor += 1
    # 归一化：一月 → 正月
    return [m.replace("一月", "正月") if m == "一月" else m for m in months]


@dataclass
class QtbjParagraph:
    season_label: str | None
    months: list[str]
    text: str
    char_start: int
    char_end: int


@dataclass
class QtbjSection:
    canonical_key: str
    book: str
    chapter_file: str
    day_gan: str
    month_zhi: str
    month_name: str
    season_label: str | None
    text: str
    fallback: bool  # True 时表示该 (day_gan, month_zhi) 没有逐月段落，回退到季节汇总
    paragraphs: list[dict] = field(default_factory=list)


# 季节 → 三个月支
SEASON_TO_MONTHS = {
    "春": ["寅", "卯", "辰"],
    "夏": ["巳", "午", "未"],
    "秋": ["申", "酉", "戌"],
    "冬": ["亥", "子", "丑"],
}


def parse_qtbj_file(rel_path: str, raw: str, day_gan: str) -> list[QtbjSection]:
    """Walk paragraphs, attach each to one or more (day_gan, month_zhi) keys."""
    season_label: str | None = None
    paragraphs: list[QtbjParagraph] = []
    cursor = 0  # char offset in raw

    # 按"段落=连续非空行"切分。空行 / heading 触发段落 flush。
    lines = raw.splitlines(keepends=True)
    buf: list[str] = []
    buf_start = 0

    def flush() -> None:
        nonlocal buf, buf_start, season_label
        if not buf:
            return
        text = "".join(buf).strip()
        if text:
            head = text[:8]  # 头几字判断月份
            months = _extract_qtbj_months(text)
            paragraphs.append(QtbjParagraph(
                season_label=season_label,
                months=months,
                text=text,
                char_start=buf_start,
                char_end=buf_start + sum(len(line) for line in buf),
            ))
        buf = []

    for line in lines:
        line_stripped = line.rstrip("\n")
        line_no_ws = line_stripped.strip()

        # heading
        if line_no_ws.startswith("#"):
            flush()
            cursor += len(line)
            buf_start = cursor
            # 仅 ### 级别 heading 视为 season label
            heading_match = re.match(r"^(#+)\s+(.*)$", line_no_ws)
            if heading_match and len(heading_match.group(1)) >= 3:
                season_label = heading_match.group(2).strip()
            continue

        # 跳过 frontmatter 字段行 (来源/编者 等)
        if re.match(r"^(来源|作者|原著|编者|评注|译者|出处|来源对照|出处对照)[:：]", line_no_ws):
            flush()
            cursor += len(line)
            buf_start = cursor
            continue

        # 空行 → flush
        if not line_no_ws:
            flush()
            cursor += len(line)
            buf_start = cursor
            continue

        # 累积
        if not buf:
            buf_start = cursor
        buf.append(line_no_ws)
        cursor += len(line)

    flush()

    # 段落延续逻辑：同一季节段内，无月份头的段落（"或..."/"若..."/"总之..."
    # /"庚丁两透..."等）归属到最近一个有月份头的段落所属月份。同时整段
    # 也累入 season_aggregate — 当某月份在源文里完全缺失（如十二月乙木），
    # 由该季节所有段落兜底。
    current_months: list[str] = []
    current_season: str | None = None
    by_month: dict[str, list[QtbjParagraph]] = {m: [] for m in QTBJ_MONTH_NAME_TO_ZHI}
    season_aggregate: dict[str, list[QtbjParagraph]] = {
        "春": [], "夏": [], "秋": [], "冬": [],
    }

    def _attach_to_season(p: QtbjParagraph) -> None:
        if not p.season_label:
            return
        for season_name in season_aggregate:
            if season_name in p.season_label:
                season_aggregate[season_name].append(p)
                return

    for p in paragraphs:
        if p.season_label and p.season_label != current_season:
            current_season = p.season_label
            current_months = []

        if p.months:
            current_months = list(p.months)
            for month in p.months:
                if month in by_month:
                    by_month[month].append(p)
        elif current_months:
            for month in current_months:
                if month in by_month:
                    by_month[month].append(p)
        # 无论是否有月份头, 段落都累入季节聚合 — 单月缺失时整季兜底
        _attach_to_season(p)

    sections: list[QtbjSection] = []
    seen_zhi: set[str] = set()
    canonical_months = [
        "正月", "二月", "三月", "四月", "五月", "六月",
        "七月", "八月", "九月", "十月", "十一月", "十二月",
    ]
    for month_name in canonical_months:
        zhi = QTBJ_MONTH_NAME_TO_ZHI[month_name]
        if zhi in seen_zhi:
            continue
        seen_zhi.add(zhi)
        ps = list(by_month.get(month_name) or [])
        is_fallback = False
        if not ps:
            season_ps: list[QtbjParagraph] = []
            for season_name, zhis in SEASON_TO_MONTHS.items():
                if zhi in zhis:
                    season_ps = season_aggregate.get(season_name, [])
                    break
            if not season_ps:
                logger.warning("QTBJ %s %s: no paragraphs found (no season fallback)",
                               day_gan, month_name)
                continue
            ps = season_ps
            is_fallback = True
            logger.debug("QTBJ %s %s: using season fallback (%d paragraphs)",
                         day_gan, month_name, len(ps))
        joined_text = "\n\n".join(p.text for p in ps)
        season = next((p.season_label for p in ps if p.season_label), None)
        sections.append(QtbjSection(
            canonical_key=f"qtbj::{day_gan}::{zhi}",
            book="qiongtong-baojian",
            chapter_file=f"qiongtong-baojian/{Path(rel_path).name}",
            day_gan=day_gan,
            month_zhi=zhi,
            month_name=month_name,
            season_label=season,
            text=joined_text,
            fallback=is_fallback,
            paragraphs=[
                {
                    "char_start": p.char_start,
                    "char_end": p.char_end,
                    "text": p.text,
                }
                for p in ps
            ],
        ))
    return sections


def build_qtbj_index(classics_root: Path) -> list[QtbjSection]:
    out: list[QtbjSection] = []
    book_dir = classics_root / "qiongtong-baojian"
    for fname, day_gan in QTBJ_FILE_TO_GAN.items():
        path = book_dir / fname
        raw = path.read_text(encoding="utf-8")
        sections = parse_qtbj_file(fname, raw, day_gan)
        logger.info("QTBJ %s (%s): %d sections", day_gan, fname, len(sections))
        out.extend(sections)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SMTH — 三命通会 卷八/卷九
# ─────────────────────────────────────────────────────────────────────────────

# 已 / 巳 在卷九目录里都被用来代表 己 (jǐ)。OCR 错字。
SMTH_DAY_GAN_NORMALIZE = {"已": "己", "巳": "己"}
# 夘 是 卯 的异体字。
SMTH_HOUR_ZHI_NORMALIZE = {"夘": "卯"}

# section heading: "六{day_gan}日{hour_gan?}{hour_zhi}時斷"
SMTH_SECTION_RE = re.compile(
    r"^##\s+六([甲乙丙丁戊己庚辛壬癸已巳])日"
    r"([甲乙丙丁戊己庚辛壬癸])?([子丑寅卯辰巳午未申酉戌亥夘])時斷"
)

# 段首条目: "<day_gan><day_zhi>日<hour_gan?><hour_zhi>時..."
# 兼容前导全角空格 / 半角空格
SMTH_ENTRY_RE = re.compile(
    r"^[\s　]*([甲乙丙丁戊己庚辛壬癸])([子丑寅卯辰巳午未申酉戌亥夘])日"
    r"([甲乙丙丁戊己庚辛壬癸])?([子丑寅卯辰巳午未申酉戌亥夘])時(.+)$"
)


@dataclass
class SmthEntry:
    canonical_key: str
    book: str
    chapter_file: str
    volume: str
    day_gan: str
    day_zhi: str
    day_pillar: str
    hour_gan: str
    hour_zhi: str
    hour_pillar: str
    section_heading: str
    text: str
    char_start: int
    char_end: int
    ocr_hour_gan: str | None = None  # 源文里写错的 hour_gan,canonical 已用五鼠遁修正


def parse_smth_file(rel_path: str, raw: str, volume: str) -> list[SmthEntry]:
    out: list[SmthEntry] = []
    cur_section_heading: str | None = None
    cur_section_day_gan: str | None = None
    cur_section_hour_zhi: str | None = None

    cursor = 0
    for line in raw.splitlines(keepends=True):
        line_no_nl = line.rstrip("\n")
        line_start = cursor
        cursor += len(line)

        # 标准 section heading
        sec_match = SMTH_SECTION_RE.match(line_no_nl)
        if sec_match:
            raw_day_gan = sec_match.group(1)
            raw_hour_zhi = sec_match.group(3)
            cur_section_heading = line_no_nl.lstrip("#").strip()
            cur_section_day_gan = SMTH_DAY_GAN_NORMALIZE.get(raw_day_gan, raw_day_gan)
            cur_section_hour_zhi = SMTH_HOUR_ZHI_NORMALIZE.get(raw_hour_zhi, raw_hour_zhi)
            continue

        # OCR 异常: ## X日YZ時... 把单条 entry 当 heading 渲染
        # 既要切到对应 (day_gan, hour_zhi) section, 又要把本行作为 entry 入帐
        if line_no_nl.startswith("##"):
            stripped = line_no_nl.lstrip("#").strip()
            entry_anomaly = SMTH_ENTRY_RE.match(stripped)
            if entry_anomaly:
                anom_day_gan = SMTH_DAY_GAN_NORMALIZE.get(
                    entry_anomaly.group(1), entry_anomaly.group(1),
                )
                anom_hour_zhi = SMTH_HOUR_ZHI_NORMALIZE.get(
                    entry_anomaly.group(4), entry_anomaly.group(4),
                )
                cur_section_heading = stripped
                cur_section_day_gan = anom_day_gan
                cur_section_hour_zhi = anom_hour_zhi
                # 不 continue — 让下面 entry 解析逻辑处理本行 (剥掉 ## 前缀)
                line_no_nl = stripped

        # 必须在 section 内才尝试匹配条目
        if cur_section_day_gan is None or cur_section_hour_zhi is None:
            continue

        # 跳过注解行
        if line_no_nl.lstrip().startswith("（注") or line_no_nl.lstrip().startswith("(注"):
            continue

        entry_match = SMTH_ENTRY_RE.match(line_no_nl)
        if not entry_match:
            continue

        raw_day_gan = entry_match.group(1)
        raw_day_zhi = entry_match.group(2)
        raw_hour_gan_opt = entry_match.group(3)  # may be None
        raw_hour_zhi = entry_match.group(4)
        body = entry_match.group(5).strip()

        day_gan = SMTH_DAY_GAN_NORMALIZE.get(raw_day_gan, raw_day_gan)
        day_zhi = SMTH_HOUR_ZHI_NORMALIZE.get(raw_day_zhi, raw_day_zhi)
        hour_zhi = SMTH_HOUR_ZHI_NORMALIZE.get(raw_hour_zhi, raw_hour_zhi)

        # 校验: 条目 day_gan 必须等于 section day_gan, 且 hour_zhi 必须等于 section hour_zhi
        if day_gan != cur_section_day_gan or hour_zhi != cur_section_hour_zhi:
            logger.debug(
                "skip mismatched entry in %s: section=(%s日,%s時) entry=(%s%s日,%s%s時)",
                rel_path, cur_section_day_gan, cur_section_hour_zhi,
                day_gan, day_zhi,
                raw_hour_gan_opt or "?", hour_zhi,
            )
            continue

        # canonical hour_gan 一律由五鼠遁推算 — OCR 在卷九里把不少 hour_gan
        # 写错(如 己日丑時 写成 乙丑時)。源文 raw_hour_gan_opt 仅做诊断保留。
        hour_gan = hour_pillar_for(day_gan, hour_zhi)[0]
        ocr_hour_gan: str | None = None
        if raw_hour_gan_opt:
            normalized = SMTH_DAY_GAN_NORMALIZE.get(raw_hour_gan_opt, raw_hour_gan_opt)
            if normalized != hour_gan:
                ocr_hour_gan = normalized

        day_pillar = day_gan + day_zhi
        hour_pillar = hour_gan + hour_zhi
        # 整条文本含日柱时柱前缀 — 给 eval 做 phrase match 用
        full_text = f"{day_pillar}日{hour_pillar}時{body}"

        out.append(SmthEntry(
            canonical_key=f"smth::{volume}::{day_pillar}::{hour_pillar}",
            book="sanming-tonghui",
            chapter_file=f"sanming-tonghui/{Path(rel_path).name}",
            volume=volume,
            day_gan=day_gan,
            day_zhi=day_zhi,
            day_pillar=day_pillar,
            hour_gan=hour_gan,
            hour_zhi=hour_zhi,
            hour_pillar=hour_pillar,
            section_heading=cur_section_heading or "",
            text=full_text,
            char_start=line_start,
            char_end=line_start + len(line_no_nl),
            ocr_hour_gan=ocr_hour_gan,
        ))
    return out


def build_smth_index(classics_root: Path) -> list[SmthEntry]:
    out: list[SmthEntry] = []
    for fname, volume in [("juan-08.md", "卷08"), ("juan-09.md", "卷09")]:
        path = classics_root / "sanming-tonghui" / fname
        raw = path.read_text(encoding="utf-8")
        entries = parse_smth_file(fname, raw, volume)
        logger.info("SMTH %s: %d entries", fname, len(entries))
        out.extend(entries)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Shensha (神煞) — Phase B
# ─────────────────────────────────────────────────────────────────────────────

from scripts.eval.extract_sections import section_index, parse_sections  # noqa: E402

# canonical term → (aliases, primary_source spec, supplementary_source specs)
# 每个 source spec = (book_dir, file_name, heading)
_SHENSHA_SPEC = [
    {
        "term": "天乙贵人", "aliases": ["天乙", "贵人", "天乙贵人"],
        "sources": [("sanming-tonghui", "juan-03.md", "論天乙貴人")],
    },
    {
        "term": "驿马", "aliases": ["驿马", "驛馬", "馬", "马"],
        "sources": [("sanming-tonghui", "juan-03.md", "論驛馬")],
    },
    {
        "term": "金舆", "aliases": ["金舆", "金轝"],
        "sources": [("sanming-tonghui", "juan-03.md", "論金轝")],
    },
    {
        "term": "天月德", "aliases": ["天德", "月德", "天月德", "二德"],
        "sources": [("sanming-tonghui", "juan-03.md", "論天月徳")],
    },
    {
        "term": "三奇", "aliases": ["三奇"],
        "sources": [("sanming-tonghui", "juan-03.md", "論三奇")],
    },
    {
        "term": "太极贵人", "aliases": ["太极贵", "太极贵人"],
        "sources": [("sanming-tonghui", "juan-03.md", "論太極貴")],
    },
    {
        "term": "学堂", "aliases": ["学堂", "词馆", "学堂词馆"],
        "sources": [("sanming-tonghui", "juan-03.md", "論學堂詞館")],
    },
    {
        "term": "德秀", "aliases": ["德秀", "德秀贵人"],
        "sources": [("sanming-tonghui", "juan-03.md", "論徳秀")],
    },
    {
        "term": "劫煞", "aliases": ["劫煞", "刼煞"],
        "sources": [("sanming-tonghui", "juan-03.md", "論刼煞亡神")],
    },
    {
        "term": "亡神", "aliases": ["亡神"],
        "sources": [("sanming-tonghui", "juan-03.md", "論刼煞亡神")],
    },
    {
        "term": "羊刃", "aliases": ["羊刃", "阳刃"],
        "sources": [
            ("sanming-tonghui", "juan-03.md", "論羊刃"),
            ("yuanhai-ziping",
             "09_shen-sha_yang-ren-ri-ren-ri-gui-ri-de-kui-gang-jin-shen.md",
             "论阳刃"),
        ],
    },
    {
        "term": "元辰", "aliases": ["元辰"],
        "sources": [("sanming-tonghui", "juan-03.md", "論元辰")],
    },
    {
        "term": "暗金的煞", "aliases": ["暗金的煞", "暗金"],
        "sources": [("sanming-tonghui", "juan-03.md", "論暗金的煞")],
    },
    {
        "term": "六厄", "aliases": ["六厄"],
        "sources": [("sanming-tonghui", "juan-03.md", "論六厄")],
    },
    {
        "term": "勾绞", "aliases": ["勾绞", "勾絞"],
        "sources": [("sanming-tonghui", "juan-03.md", "論勾絞")],
    },
    {
        "term": "孤辰寡宿", "aliases": ["孤辰", "寡宿", "孤辰寡宿"],
        "sources": [("sanming-tonghui", "juan-03.md", "論孤辰寡宿")],
    },
    {
        "term": "天罗地网", "aliases": ["天罗", "地网", "天罗地网"],
        "sources": [("sanming-tonghui", "juan-03.md", "論天羅地網")],
    },
    {
        "term": "十恶大败", "aliases": ["十恶大败"],
        "sources": [("sanming-tonghui", "juan-03.md", "論十惡大敗")],
    },
    # 渊海 09 独有 / 主源
    {
        "term": "日刃", "aliases": ["日刃"],
        "sources": [("yuanhai-ziping",
                     "09_shen-sha_yang-ren-ri-ren-ri-gui-ri-de-kui-gang-jin-shen.md",
                     "论日刃")],
    },
    {
        "term": "日贵", "aliases": ["日贵", "日贵人"],
        "sources": [("yuanhai-ziping",
                     "09_shen-sha_yang-ren-ri-ren-ri-gui-ri-de-kui-gang-jin-shen.md",
                     "论日贵")],
    },
    {
        "term": "日德", "aliases": ["日德"],
        "sources": [("yuanhai-ziping",
                     "09_shen-sha_yang-ren-ri-ren-ri-gui-ri-de-kui-gang-jin-shen.md",
                     "论日德")],
    },
    {
        "term": "魁罡", "aliases": ["魁罡"],
        "sources": [("yuanhai-ziping",
                     "09_shen-sha_yang-ren-ri-ren-ri-gui-ri-de-kui-gang-jin-shen.md",
                     "论魁罡")],
    },
    {
        "term": "金神", "aliases": ["金神"],
        "sources": [("yuanhai-ziping",
                     "09_shen-sha_yang-ren-ri-ren-ri-gui-ri-de-kui-gang-jin-shen.md",
                     "论金神")],
    },
    # 禄: SMTH 论十干禄
    {
        "term": "禄", "aliases": ["禄", "禄神", "建禄", "天禄"],
        "sources": [("sanming-tonghui", "juan-03.md", "論十干祿")],
    },
    # 高频神煞补充 — 用户最常问的 4 项
    {
        "term": "桃花", "aliases": ["桃花", "咸池", "桃花煞", "桃花运",
                                    "烂桃花", "正桃花", "好桃花"],
        # 卷二 "論咸池" 是正源 — 文中明确"咸池一名桃花煞"
        "sources": [("sanming-tonghui", "juan-02.md", "論咸池")],
    },
    {
        "term": "华盖", "aliases": ["华盖", "華蓋", "華葢"],
        "sources": [("sanming-tonghui", "juan-02.md", "論將星華葢")],
    },
    {
        "term": "将星", "aliases": ["将星", "將星", "将", "将星扶德"],
        "sources": [
            ("sanming-tonghui", "juan-02.md", "論將星華葢"),
            ("sanming-tonghui", "juan-06.md", "將星扶德"),
        ],
    },
    {
        "term": "空亡", "aliases": ["空亡", "旬空", "空", "落空"],
        "sources": [("sanming-tonghui", "juan-10.md",
                     "空亡消息數端豈止十干缺處")],
    },
]


@dataclass
class ShenshaEntry:
    canonical_key: str
    term: str
    aliases: list[str]
    book: str
    chapter_file: str
    heading: str
    text: str
    char_start: int
    char_end: int
    secondary_sources: list[dict] = field(default_factory=list)


def build_shensha_index(classics_root: Path) -> list[ShenshaEntry]:
    out: list[ShenshaEntry] = []
    cache: dict[str, dict[str, "object"]] = {}  # path → section_index

    def get_section(book: str, fname: str, heading: str):
        path = classics_root / book / fname
        key = str(path)
        if key not in cache:
            cache[key] = section_index(path)
        return cache[key].get(heading)

    for spec in _SHENSHA_SPEC:
        sources = spec["sources"]
        primary = sources[0]
        prim_section = get_section(*primary)
        if prim_section is None:
            logger.warning("shensha %s: primary source %s/%s heading %s not found",
                           spec["term"], *primary)
            continue

        # 二级源
        sec_blocks: list[dict] = []
        for src in sources[1:]:
            sec_section = get_section(*src)
            if sec_section is None:
                logger.warning("shensha %s: secondary %s/%s/%s missing",
                               spec["term"], *src)
                continue
            sec_blocks.append({
                "book": src[0],
                "chapter_file": f"{src[0]}/{src[1]}",
                "heading": sec_section.heading,
                "text": sec_section.body,
            })

        out.append(ShenshaEntry(
            canonical_key=f"shensha::{spec['term']}",
            term=spec["term"],
            aliases=list(spec["aliases"]),
            book=primary[0],
            chapter_file=f"{primary[0]}/{primary[1]}",
            heading=prim_section.heading,
            text=prim_section.body,
            char_start=prim_section.char_start,
            char_end=prim_section.char_end,
            secondary_sources=sec_blocks,
        ))
    logger.info("shensha: %d canonical terms", len(out))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Geju (格局) — Phase C
# ─────────────────────────────────────────────────────────────────────────────

# 子平真诠 各格 chapter pairs: 论X + 论X取运 = 一个canonical 格局 bundle
_GEJU_SPEC = [
    {"name": "正官格", "aliases": ["正官", "官格"],
     "files": ["31_lun-zheng-guan.md", "32_lun-zheng-guan-qu-yun.md"]},
    {"name": "财格", "aliases": ["财格", "正财格", "偏财格"],
     "files": ["33_lun-cai.md", "34_lun-cai-qu-yun.md"]},
    {"name": "印绶格", "aliases": ["印绶格", "印格", "正印格", "偏印格"],
     "files": ["35_lun-yin-shou.md", "36_lun-yin-shou-qu-yun.md"]},
    {"name": "食神格", "aliases": ["食神格"],
     "files": ["37_lun-shi-shen.md", "38_lun-shi-shen-qu-yun.md"]},
    {"name": "偏官格", "aliases": ["偏官格", "七杀格", "煞格"],
     "files": ["39_lun-pian-guan.md", "40_lun-pian-guan-qu-yun.md"]},
    {"name": "伤官格", "aliases": ["伤官格", "伤官"],
     "files": ["41_lun-shang-guan.md", "42_lun-shang-guan-qu-yun.md"]},
    {"name": "阳刃格", "aliases": ["阳刃格", "羊刃格"],
     "files": ["43_lun-yang-ren.md", "44_lun-yang-ren-qu-yun.md"]},
    {"name": "建禄月劫格", "aliases": ["建禄格", "月劫格", "建禄月劫"],
     "files": ["45_lun-jian-lu-yue-jie.md", "46_lun-jian-lu-yue-jie-qu-yun.md"]},
    {"name": "杂格", "aliases": ["杂格", "外格", "特殊格局"],
     "files": ["47_lun-za-ge.md", "48_lun-za-ge-qu-yun.md"]},
]


@dataclass
class GejuEntry:
    canonical_key: str
    name: str
    aliases: list[str]
    book: str
    chapter_files: list[str]
    text: str  # 拼接所有相关 chapter 的 body
    char_start: int
    char_end: int


def build_geju_index(classics_root: Path) -> list[GejuEntry]:
    out: list[GejuEntry] = []
    book = "ziping-zhenquan"
    book_dir = classics_root / book
    for spec in _GEJU_SPEC:
        chapter_files = []
        bodies = []
        first_start = -1
        last_end = 0
        for fname in spec["files"]:
            path = book_dir / fname
            if not path.exists():
                logger.warning("geju %s: file %s not found", spec["name"], fname)
                continue
            raw = path.read_text(encoding="utf-8")
            sections = parse_sections(raw, min_level=1, max_level=2)
            # 取第一个 ##/# section (整章是一个段)
            if sections:
                body = sections[0].body
                if body:
                    chapter_files.append(f"{book}/{fname}")
                    bodies.append(body)
                    if first_start < 0:
                        first_start = sections[0].char_start
                    last_end = sections[0].char_end
        if not bodies:
            logger.warning("geju %s: no content extracted", spec["name"])
            continue
        out.append(GejuEntry(
            canonical_key=f"geju::{spec['name']}",
            name=spec["name"],
            aliases=list(spec["aliases"]),
            book=book,
            chapter_files=chapter_files,
            text="\n\n".join(bodies),
            char_start=first_start if first_start >= 0 else 0,
            char_end=last_end,
        ))
    logger.info("geju: %d canonical entries", len(out))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Liuqin (六亲) — Phase E
# ─────────────────────────────────────────────────────────────────────────────

_LIUQIN_SPEC = [
    {
        "relation": "夫妻",
        "aliases": ["夫妻", "妻", "夫", "配偶", "妻妾", "老婆", "老公",
                    "丈夫", "媳妇", "婚姻", "感情", "正缘"],
        "sources": [
            ("yuanhai-ziping", "10_liu-qin-lun.md", "论妻妾"),
            ("ziping-zhenquan", "23_lun-gong-fen-yong-shen-pei-liu-qin.md", None),
            ("ziping-zhenquan", "24_lun-qi-zi.md", None),
        ],
    },
    {
        "relation": "子女", "aliases": ["子女", "子", "子息", "儿女"],
        "sources": [
            ("yuanhai-ziping", "10_liu-qin-lun.md", "论子息"),
            ("ziping-zhenquan", "24_lun-qi-zi.md", None),
        ],
    },
    {
        "relation": "父", "aliases": ["父", "父亲"],
        "sources": [("yuanhai-ziping", "10_liu-qin-lun.md", "论父")],
    },
    {
        "relation": "母", "aliases": ["母", "母亲"],
        "sources": [("yuanhai-ziping", "10_liu-qin-lun.md", "论母")],
    },
    {
        "relation": "兄弟", "aliases": ["兄弟", "姊妹", "兄弟姊妹"],
        "sources": [("yuanhai-ziping", "10_liu-qin-lun.md", "论兄弟姊妹")],
    },
    {
        "relation": "六亲总论", "aliases": ["六亲", "六亲总论"],
        "sources": [
            ("yuanhai-ziping", "10_liu-qin-lun.md", "六亲总篇"),
        ],
    },
]


@dataclass
class LiuqinEntry:
    canonical_key: str
    relation: str
    aliases: list[str]
    book: str
    chapter_files: list[str]
    text: str
    char_start: int
    char_end: int


def build_liuqin_index(classics_root: Path) -> list[LiuqinEntry]:
    out: list[LiuqinEntry] = []
    section_cache: dict[str, dict[str, "object"]] = {}

    def all_sections(book: str, fname: str):
        key = f"{book}/{fname}"
        if key not in section_cache:
            path = classics_root / book / fname
            section_cache[key] = section_index(path)
        return section_cache[key]

    for spec in _LIUQIN_SPEC:
        bodies: list[str] = []
        chapter_files: list[str] = []
        first_start = -1
        last_end = 0

        for src in spec["sources"]:
            book, fname, heading = src
            path = classics_root / book / fname
            if not path.exists():
                continue
            if heading is None:
                # 整文件作为一段 (论妻子 / 论宫分配六亲)
                raw = path.read_text(encoding="utf-8")
                secs = parse_sections(raw, min_level=1, max_level=2)
                if secs and secs[0].body:
                    bodies.append(secs[0].body)
                    chapter_files.append(f"{book}/{fname}")
                    if first_start < 0:
                        first_start = secs[0].char_start
                    last_end = secs[0].char_end
            else:
                section = all_sections(book, fname).get(heading)
                if section is None:
                    logger.warning("liuqin %s: %s/%s heading %s missing",
                                   spec["relation"], book, fname, heading)
                    continue
                bodies.append(section.body)
                chapter_files.append(f"{book}/{fname}")
                if first_start < 0:
                    first_start = section.char_start
                last_end = section.char_end

        if not bodies:
            logger.warning("liuqin %s: no content", spec["relation"])
            continue
        out.append(LiuqinEntry(
            canonical_key=f"liuqin::{spec['relation']}",
            relation=spec["relation"],
            aliases=list(spec["aliases"]),
            book="multi" if len(set(c.split("/")[0] for c in chapter_files)) > 1
                  else chapter_files[0].split("/")[0],
            chapter_files=chapter_files,
            text="\n\n".join(bodies),
            char_start=first_start if first_start >= 0 else 0,
            char_end=last_end,
        ))
    logger.info("liuqin: %d canonical entries", len(out))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Appearance (外貌) — Phase F
# ─────────────────────────────────────────────────────────────────────────────

# 渊海子平 04 干支体象: 10 天干 + 12 地支 = 22 entries
# 三命通会 卷7 论性情相貌 = 1 entry (主源 — 性情+外貌)
_APPEARANCE_GAN_RE = re.compile(r"^(?:[甲乙丙丁戊己庚辛壬癸])(?:[木火土金水])\s*[:：]")
_APPEARANCE_ZHI_RE = re.compile(r"^(?:[子丑寅卯辰巳午未申酉戌亥])\s*[:：]")


@dataclass
class AppearanceEntry:
    canonical_key: str
    aspect: str  # day_gan name (甲) / day_zhi name (子) / general
    kind: str    # "gan" / "zhi" / "general"
    book: str
    chapter_file: str
    text: str
    char_start: int
    char_end: int


_TIXIANG_LINE_RE = re.compile(r"^《([甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥])》(.+)$")


def _parse_yhzp_tixiang(raw: str, kind: str, axis_chars: str) -> list[tuple[str, str, int, int]]:
    """渊海子平 04 干支体象解析。

    源文格式: 一行一条,以《X》开头,如:
        《甲》甲木天干作首排,原无枝叶与根荄;...
        《乙》乙木根荄种得深...
    """
    out: list[tuple[str, str, int, int]] = []
    cursor = 0
    for line in raw.splitlines(keepends=True):
        line_strip = line.rstrip("\n").strip()
        line_start = cursor
        cursor += len(line)
        if not line_strip or not line_strip.startswith("《"):
            continue
        m = _TIXIANG_LINE_RE.match(line_strip)
        if not m:
            continue
        axis = m.group(1)
        if axis not in axis_chars:
            continue
        out.append((axis, line_strip, line_start, line_start + len(line_strip)))
    return out


def build_appearance_index(classics_root: Path) -> list[AppearanceEntry]:
    out: list[AppearanceEntry] = []
    yhzp = classics_root / "yuanhai-ziping" / "04_gan-zhi-ti-xiang.md"
    if yhzp.exists():
        raw = yhzp.read_text(encoding="utf-8")
        # 干 部分 (## 天干体象) 和 支 部分 (## 地支体象) 分开解析
        sections = parse_sections(raw)
        for section in sections:
            if section.heading == "天干体象":
                for axis, body, cs, ce in _parse_yhzp_tixiang(section.body, "gan", "甲乙丙丁戊己庚辛壬癸"):
                    out.append(AppearanceEntry(
                        canonical_key=f"appearance::gan::{axis}",
                        aspect=axis, kind="gan",
                        book="yuanhai-ziping",
                        chapter_file="yuanhai-ziping/04_gan-zhi-ti-xiang.md",
                        text=body, char_start=section.char_start + cs,
                        char_end=section.char_start + ce,
                    ))
            elif section.heading == "地支体象":
                for axis, body, cs, ce in _parse_yhzp_tixiang(section.body, "zhi", "子丑寅卯辰巳午未申酉戌亥"):
                    out.append(AppearanceEntry(
                        canonical_key=f"appearance::zhi::{axis}",
                        aspect=axis, kind="zhi",
                        book="yuanhai-ziping",
                        chapter_file="yuanhai-ziping/04_gan-zhi-ti-xiang.md",
                        text=body, char_start=section.char_start + cs,
                        char_end=section.char_start + ce,
                    ))

    # 三命通会 卷7 论性情相貌 (general 性情 + 外貌)
    smth7 = classics_root / "sanming-tonghui" / "juan-07.md"
    if smth7.exists():
        sections = section_index(smth7)
        s = sections.get("論性情相貌")
        if s and s.body:
            out.append(AppearanceEntry(
                canonical_key="appearance::general::xing-qing-xiang-mao",
                aspect="general", kind="general",
                book="sanming-tonghui",
                chapter_file="sanming-tonghui/juan-07.md",
                text=s.body, char_start=s.char_start, char_end=s.char_end,
            ))
    logger.info("appearance: %d canonical entries", len(out))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Concept (概念) — Phase H
# ─────────────────────────────────────────────────────────────────────────────

# 把"什么是X"的命理基础概念绑定到权威定义。
# 渊海子平 05-08 = 十神 (10 神 + 总论)
# 子平真诠 01-08 = 干支阴阳 + 用神基础
_CONCEPT_SPEC = [
    # 十神 — 渊海子平 + 子平真诠 论用神
    {"term": "正官", "aliases": ["正官", "官"],
     "sources": [("ziping-zhenquan", "31_lun-zheng-guan.md", None),
                 ("yuanhai-ziping", "07_shi-shen_zheng-guan-pian-guan-qi-sha.md",
                  "论正官")]},
    {"term": "七杀", "aliases": ["七杀", "偏官", "煞", "杀"],
     "sources": [("ziping-zhenquan", "39_lun-pian-guan.md", None),
                 ("yuanhai-ziping", "07_shi-shen_zheng-guan-pian-guan-qi-sha.md",
                  "论七杀")]},
    {"term": "正财", "aliases": ["正财"],
     "sources": [("yuanhai-ziping", "06_shi-shen_zheng-cai-pian-cai.md", "论正财")]},
    {"term": "偏财", "aliases": ["偏财"],
     "sources": [("yuanhai-ziping", "06_shi-shen_zheng-cai-pian-cai.md", "论偏财")]},
    {"term": "食神", "aliases": ["食神"],
     "sources": [("ziping-zhenquan", "37_lun-shi-shen.md", None),
                 ("yuanhai-ziping", "05_shi-shen_shang-guan-shi-shen.md", "论食神")]},
    {"term": "伤官", "aliases": ["伤官"],
     "sources": [("ziping-zhenquan", "41_lun-shang-guan.md", None),
                 ("yuanhai-ziping", "05_shi-shen_shang-guan-shi-shen.md", "论伤官")]},
    {"term": "正印", "aliases": ["正印", "印绶", "印綬"],
     "sources": [("yuanhai-ziping", "08_shi-shen_yin-shou-dao-shi-jie-cai.md",
                  "论印綬")]},
    {"term": "偏印", "aliases": ["偏印", "倒食", "枭神"],
     "sources": [("yuanhai-ziping", "08_shi-shen_yin-shou-dao-shi-jie-cai.md",
                  "论倒食")]},
    # 比肩在原文未单列章节,与劫财合论,故合并到劫财 entry,aliases 兼收
    {"term": "比肩劫财", "aliases": ["比肩", "劫财"],
     "sources": [("yuanhai-ziping", "08_shi-shen_yin-shou-dao-shi-jie-cai.md",
                  "论劫财")]},
    # 基础概念
    {"term": "十干十二支", "aliases": ["十干", "十二支", "天干地支"],
     "sources": [("ziping-zhenquan", "01_lun-shi-gan-shi-er-zhi.md", None)]},
    {"term": "阴阳生克", "aliases": ["阴阳生克", "五行生克", "生克"],
     "sources": [("ziping-zhenquan", "02_lun-yin-yang-sheng-ke.md", None)]},
    {"term": "阴阳生死", "aliases": ["阴阳生死", "十二长生", "长生"],
     "sources": [("ziping-zhenquan", "03_lun-yin-yang-sheng-si.md", None)]},
    {"term": "十干配合", "aliases": ["十干配合", "天干合", "干合"],
     "sources": [("ziping-zhenquan", "04_lun-shi-gan-pei-he-xing-qing.md", None)]},
    {"term": "十干合而不合", "aliases": ["合而不合", "合而不化"],
     "sources": [("ziping-zhenquan", "05_lun-shi-gan-he-er-bu-he.md", None)]},
    {"term": "刑冲会合", "aliases": ["刑冲", "冲", "刑", "会合", "刑冲会合"],
     "sources": [("ziping-zhenquan", "07_lun-xing-chong-hui-he-xie-fa.md", None)]},
    {"term": "用神", "aliases": ["用神"],
     "sources": [("ziping-zhenquan", "08_lun-yong-shen.md", None)]},
    {"term": "相神", "aliases": ["相神"],
     "sources": [("ziping-zhenquan", "15_lun-xiang-shen-jin-yao.md", None)]},
    {"term": "用神成败", "aliases": ["用神成败", "成格", "破格", "成败救应"],
     "sources": [("ziping-zhenquan", "09_lun-yong-shen-cheng-bai-jiu-ying.md", None)]},
    {"term": "用神变化", "aliases": ["用神变化"],
     "sources": [("ziping-zhenquan", "10_lun-yong-shen-bian-hua.md", None)]},
    {"term": "格局高低", "aliases": ["格局高低"],
     "sources": [("ziping-zhenquan", "12_lun-yong-shen-ge-ju-gao-di.md", None)]},
    {"term": "调候", "aliases": ["调候", "气候得失"],
     "sources": [("ziping-zhenquan", "14_lun-yong-shen-pei-qi-hou-de-shi.md", None)]},
    {"term": "杂气", "aliases": ["杂气"],
     "sources": [("ziping-zhenquan", "16_lun-za-qi-ru-he-qu-yong.md", None)]},
    {"term": "得时不旺失时不弱", "aliases": ["得时不旺失时不弱", "旺衰"],
     "sources": [("ziping-zhenquan",
                  "06_lun-shi-gan-de-shi-bu-wang-shi-shi-bu-ruo.md", None)]},
    {"term": "行运", "aliases": ["行运", "大运", "流年"],
     "sources": [("ziping-zhenquan", "25_lun-xing-yun.md", None)]},
]


@dataclass
class ConceptEntry:
    canonical_key: str
    term: str
    aliases: list[str]
    book: str
    chapter_files: list[str]
    text: str
    char_start: int
    char_end: int


def build_concept_index(classics_root: Path) -> list[ConceptEntry]:
    out: list[ConceptEntry] = []
    section_cache: dict[str, dict[str, "object"]] = {}

    def all_sections(book: str, fname: str):
        key = f"{book}/{fname}"
        if key not in section_cache:
            path = classics_root / book / fname
            if not path.exists():
                section_cache[key] = {}
            else:
                section_cache[key] = section_index(path)
        return section_cache[key]

    for spec in _CONCEPT_SPEC:  # noqa
        bodies: list[str] = []
        chapter_files: list[str] = []
        first_start = -1
        last_end = 0

        for src in spec["sources"]:
            book, fname, heading = src
            path = classics_root / book / fname
            if not path.exists():
                logger.warning("concept %s: file %s/%s missing", spec["term"], book, fname)
                continue
            if heading is None:
                raw = path.read_text(encoding="utf-8")
                secs = parse_sections(raw, min_level=1, max_level=2)
                if secs and secs[0].body:
                    bodies.append(secs[0].body)
                    chapter_files.append(f"{book}/{fname}")
                    if first_start < 0:
                        first_start = secs[0].char_start
                    last_end = secs[0].char_end
            else:
                s = all_sections(book, fname).get(heading)
                if s is None:
                    logger.warning("concept %s: heading %s in %s missing",
                                   spec["term"], heading, fname)
                    continue
                bodies.append(s.body)
                chapter_files.append(f"{book}/{fname}")
                if first_start < 0:
                    first_start = s.char_start
                last_end = s.char_end

        if not bodies:
            logger.warning("concept %s: no content", spec["term"])
            continue
        out.append(ConceptEntry(
            canonical_key=f"concept::{spec['term']}",
            term=spec["term"],
            aliases=list(spec["aliases"]),
            book=chapter_files[0].split("/")[0] if chapter_files else "",
            chapter_files=chapter_files,
            text="\n\n".join(bodies),
            char_start=first_start if first_start >= 0 else 0,
            char_end=last_end,
        ))
    logger.info("concept: %d canonical entries", len(out))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Theory (理论原则) — Phase D
# ─────────────────────────────────────────────────────────────────────────────
#
# 理论原则不能像查表型那样 (key → 唯一答案),走"主题字典"路线:
# 每个 topic 预先指定 1-3 个章节区段,聚合成 evidence bundle。
# 触发: query 提到 topic 名或别名 → 返回该 topic bundle。
# 用户日志驱动迭代:覆盖不到的 query 仍走 retrieval2 selector 兜底。

# 滴天髓 通神论 / 六亲论 文件 H1 都形如 "序号、主题名",从中抽 topic name
_DTS_TOPIC_HEADING_RE = re.compile(r"^#\s+[一二三四五六七八九十百千]+、(.+?)\s*$")
_ZPZQ_TOPIC_HEADING_RE = re.compile(r"^#\s+论(.+?)\s*$")

# 已被其他家族覆盖的滴天髓节,跳过避免重复
_DTS_SKIP_FILES = {
    "tong-shen-lun_15_yue-ling.md",  # 月令 — 跟 concept 部分重叠,但 theory bundle 更完整,保留
    "liu-qin-lun_01_fu-qi.md",       # 夫妻 → liuqin 已有
    "liu-qin-lun_02_zi-nv.md",       # 子女 → liuqin 已有
    "liu-qin-lun_03_fu-mu.md",       # 父母 → liuqin 已有
    "liu-qin-lun_04_xiong-di.md",    # 兄弟 → liuqin 已有
}
# 反正 月令 在 concept 是从 子平真诠 来,这里 滴天髓 月令 论述完全不同,留着
_DTS_SKIP_FILES.discard("tong-shen-lun_15_yue-ling.md")

# 已被 concept/geju 完整覆盖的子平真诠章节,跳过
_ZPZQ_SKIP_FILES = {
    # 概念已覆盖
    "01_lun-shi-gan-shi-er-zhi.md",
    "02_lun-yin-yang-sheng-ke.md",
    "03_lun-yin-yang-sheng-si.md",
    "04_lun-shi-gan-pei-he-xing-qing.md",
    "05_lun-shi-gan-he-er-bu-he.md",
    "06_lun-shi-gan-de-shi-bu-wang-shi-shi-bu-ruo.md",
    "07_lun-xing-chong-hui-he-xie-fa.md",
    "08_lun-yong-shen.md",
    "09_lun-yong-shen-cheng-bai-jiu-ying.md",
    "10_lun-yong-shen-bian-hua.md",
    "12_lun-yong-shen-ge-ju-gao-di.md",
    "14_lun-yong-shen-pei-qi-hou-de-shi.md",
    "15_lun-xiang-shen-jin-yao.md",
    "16_lun-za-qi-ru-he-qu-yong.md",
    "25_lun-xing-yun.md",
    # 格局家族已覆盖 (论X + 论X取运)
    "31_lun-zheng-guan.md", "32_lun-zheng-guan-qu-yun.md",
    "33_lun-cai.md", "34_lun-cai-qu-yun.md",
    "35_lun-yin-shou.md", "36_lun-yin-shou-qu-yun.md",
    "37_lun-shi-shen.md", "38_lun-shi-shen-qu-yun.md",
    "39_lun-pian-guan.md", "40_lun-pian-guan-qu-yun.md",
    "41_lun-shang-guan.md", "42_lun-shang-guan-qu-yun.md",
    "43_lun-yang-ren.md", "44_lun-yang-ren-qu-yun.md",
    "45_lun-jian-lu-yue-jie.md", "46_lun-jian-lu-yue-jie-qu-yun.md",
    "47_lun-za-ge.md", "48_lun-za-ge-qu-yun.md",
    # 六亲家族已覆盖
    "23_lun-gong-fen-yong-shen-pei-liu-qin.md",
    "24_lun-qi-zi.md",
    # mu-lu / 序
    "00_mu-lu.md", "00_xu.md", "00_fan-li.md",
}

# 给主题加常用别名,提升 retriever term 命中率
_THEORY_ALIAS_MAP: dict[str, list[str]] = {
    "天道": ["天道"],
    "地道": ["地道"],
    "人道": ["人道"],
    "知命": ["知命"],
    "理气": ["理气"],
    "配合": ["配合", "干支配合"],
    "天干": ["天干"],
    "地支": ["地支"],
    "干支总论": ["干支总论"],
    "形象": ["形象", "格象"],
    "方局": ["方局", "三方", "三合"],
    "八格": ["八格", "八正格", "我什么格", "我的格局是什么"],
    "体用": ["体用", "体用论"],
    "精神": ["精神", "精气神"],
    "月令": ["月令", "提纲"],
    "生时": ["生时", "时柱"],
    "衰旺": ["衰旺", "旺衰", "得令", "失令", "旺相休囚死",
             "身强", "身弱", "我强不强", "我旺不旺"],
    "中和": ["中和", "平衡", "平不平衡"],
    "源流": ["源流"],
    "通关": ["通关", "通气", "化解"],
    "官煞": ["官煞", "官杀", "杀印", "煞印"],
    "伤官": ["伤官", "伤官见官"],
    "清气": ["清气", "清纯"],
    "浊气": ["浊气", "驳杂"],
    "真神": ["真神"],
    "假神": ["假神"],
    "刚柔": ["刚柔", "阴阳刚柔"],
    "顺逆": ["顺逆", "顺逆之机"],
    "寒暖": ["寒暖", "调候"],
    "燥湿": ["燥湿"],
    "隐显": ["隐显"],
    "众寡": ["众寡"],
    "震兑": ["震兑"],
    "坎离": ["坎离"],
    "合之章": ["合之章", "合化", "六合"],
    "女命章": ["女命", "妇人命", "我老婆", "妻子命", "女性"],
    "小儿": ["小儿", "小儿命", "孩子命", "小孩"],
    "才德": ["才德", "品德", "才华"],
    "奋郁": ["奋郁", "奋发", "郁闷"],
    "恩怨": ["恩怨", "恩仇"],
    "闲神": ["闲神", "无关神"],
    "从象": ["从象", "从格"],
    "化象": ["化象", "化格"],
    "假从": ["假从"],
    "假化": ["假化"],
    "顺局": ["顺局"],
    "反局": ["反局"],
    "战局": ["战局", "战伏"],
    "合局": ["合局"],
    "君象": ["君象"],
    "臣象": ["臣象"],
    "母象": ["母象"],
    "子象": ["子象"],
    "性情": ["性情", "性格", "脾气", "我这人", "我是不是太", "我这种人"],
    "疾病": ["疾病", "健康", "病", "生病", "身体", "失眠", "焦虑",
             "情绪", "压力大", "容易累", "亚健康"],
    "出身": ["出身", "门第", "家境", "原生家庭"],
    "地位": ["地位", "高低", "阶层"],
    "岁运": ["岁运", "大运", "流年", "今年", "明年", "后年", "未来",
             "将来", "以后", "这几年", "近几年", "什么时候", "转运",
             "走运", "运势"],
    "贞元": ["贞元"],
    "用神纯杂": ["用神纯杂", "纯杂"],
    "用神因成得败": ["因成得败", "因败得成"],
    "墓库刑冲": ["墓库刑冲", "墓库", "刑冲库"],
    "四吉神能破格": ["四吉神能破格", "吉神破格"],
    "四凶神能成格": ["四凶神能成格", "凶神成格"],
    "生克先后": ["生克先后", "生克分吉凶"],
    "星辰无关格局": ["星辰无关格局", "神煞无关"],
    "外格用舍": ["外格", "外格用舍"],
    "行运成格变格": ["行运成格", "行运变格", "运转变", "运里成格",
                     "这两年怎么样", "这一步运", "这步运", "这几年走"],
    "喜忌干支有别": ["喜忌干支有别", "干支喜忌"],
    "支中喜忌逢运透清": ["支中喜忌", "逢运透清"],
    "时说拘泥格局": ["拘泥格局"],
    "时说以讹传讹": ["以讹传讹"],
}


@dataclass
class TheoryEntry:
    canonical_key: str
    topic: str
    aliases: list[str]
    book: str
    chapter_file: str
    text: str
    char_start: int
    char_end: int


def _aliases_for(topic: str) -> list[str]:
    out = list(_THEORY_ALIAS_MAP.get(topic) or [topic])
    if topic not in out:
        out.insert(0, topic)
    return out


def _theory_topic_from_dts_file(path: Path) -> str | None:
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        m = _DTS_TOPIC_HEADING_RE.match(line.rstrip())
        if m:
            return m.group(1).strip()
    return None


def _theory_topic_from_zpzq_file(path: Path) -> str | None:
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        m = _ZPZQ_TOPIC_HEADING_RE.match(line.rstrip())
        if m:
            return m.group(1).strip()
    return None


def _theory_body_text(path: Path) -> tuple[str, int, int]:
    raw = path.read_text(encoding="utf-8")
    secs = parse_sections(raw, min_level=1, max_level=2)
    if not secs:
        return "", 0, 0
    body = secs[0].body
    return body, secs[0].char_start, secs[0].char_end


def build_theory_index(classics_root: Path) -> list[TheoryEntry]:
    out: list[TheoryEntry] = []
    seen_topics: set[str] = set()

    # 1. 滴天髓 — 通神论 + 六亲论 (按文件枚举)
    dts_dir = classics_root / "ditian-sui"
    for path in sorted(dts_dir.glob("*.md")):
        if path.name == "00_mu-lu.md":
            continue
        if path.name in _DTS_SKIP_FILES:
            continue
        topic = _theory_topic_from_dts_file(path)
        if not topic:
            logger.warning("theory dts %s: no H1 topic heading", path.name)
            continue
        if topic in seen_topics:
            topic = f"{topic}(滴天髓)"
        seen_topics.add(topic)
        body, cs, ce = _theory_body_text(path)
        if not body:
            continue
        out.append(TheoryEntry(
            canonical_key=f"theory::{topic}",
            topic=topic,
            aliases=_aliases_for(topic),
            book="ditian-sui",
            chapter_file=f"ditian-sui/{path.name}",
            text=body, char_start=cs, char_end=ce,
        ))

    # 2. 子平真诠 — 论X 系列 (排除已被 concept/geju/liuqin 覆盖的)
    zpzq_dir = classics_root / "ziping-zhenquan"
    for path in sorted(zpzq_dir.glob("*.md")):
        if path.name in _ZPZQ_SKIP_FILES:
            continue
        topic_raw = _theory_topic_from_zpzq_file(path)
        if not topic_raw:
            logger.warning("theory zpzq %s: no H1 topic heading", path.name)
            continue
        # 简化主题名: "用神成败救应" 太长,提取核心词
        topic = topic_raw
        for prefix in ("用神", "支中"):
            pass  # 保留全名,alias 里加简称
        if topic in seen_topics:
            topic = f"{topic}(子平真诠)"
        seen_topics.add(topic)
        body, cs, ce = _theory_body_text(path)
        if not body:
            continue
        out.append(TheoryEntry(
            canonical_key=f"theory::{topic}",
            topic=topic,
            aliases=_aliases_for(topic),
            book="ziping-zhenquan",
            chapter_file=f"ziping-zhenquan/{path.name}",
            text=body, char_start=cs, char_end=ce,
        ))

    # 3. 渊海子平 — 选 13 看命入式 / 14 群兴论 / 23 神弱论 等理论性章
    yhzp_theory_files = [
        ("13_kan-ming-ru-shi-shen-qu-ba-fa-za-lun.md", "看命入式"),
        ("14_qun-xing-lun-xing-wang-bao-fa-cun-jin.md", "群兴论"),
        ("23_shen-ruo-lun-qi-ming-cong-sha-lun.md", "神弱论"),
    ]
    for fname, topic in yhzp_theory_files:
        path = classics_root / "yuanhai-ziping" / fname
        if not path.exists():
            continue
        if topic in seen_topics:
            topic = f"{topic}(渊海)"
        seen_topics.add(topic)
        body, cs, ce = _theory_body_text(path)
        if not body:
            continue
        out.append(TheoryEntry(
            canonical_key=f"theory::{topic}",
            topic=topic,
            aliases=_aliases_for(topic),
            book="yuanhai-ziping",
            chapter_file=f"yuanhai-ziping/{fname}",
            text=body, char_start=cs, char_end=ce,
        ))

    logger.info("theory: %d canonical entries", len(out))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 完整性校验
# ─────────────────────────────────────────────────────────────────────────────

def expected_qtbj_keys() -> list[str]:
    out = []
    for g in GAN:
        for z in ZHI:
            out.append(f"qtbj::{g}::{z}")
    return out


def expected_smth_keys() -> list[str]:
    """所有 60 日柱 × 12 时支 → 720 条 (干支配对必须合法 — 60 个有效日柱)."""
    out = []
    for d_idx in range(60):
        day_gan = GAN[d_idx % 10]
        day_zhi = ZHI[d_idx % 12]
        for hour_zhi in ZHI:
            hour_pillar = hour_pillar_for(day_gan, hour_zhi)
            day_pillar = day_gan + day_zhi
            # 卷08覆盖甲乙丙丁戊, 卷09覆盖己庚辛壬癸
            volume = "卷08" if day_gan in {"甲", "乙", "丙", "丁", "戊"} else "卷09"
            out.append(f"smth::{volume}::{day_pillar}::{hour_pillar}")
    return out


def diff_keys(found: Iterable[str], expected: Iterable[str]) -> tuple[list[str], list[str]]:
    found_s = set(found)
    expected_s = set(expected)
    missing = sorted(expected_s - found_s)
    extra = sorted(found_s - expected_s)
    return missing, extra


# ─────────────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classics", type=Path, default=CLASSICS_ROOT)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    qtbj = build_qtbj_index(args.classics)
    smth = build_smth_index(args.classics)
    shensha = build_shensha_index(args.classics)
    geju = build_geju_index(args.classics)
    liuqin = build_liuqin_index(args.classics)
    appearance = build_appearance_index(args.classics)
    concept = build_concept_index(args.classics)
    theory = build_theory_index(args.classics)

    qtbj_missing, qtbj_extra = diff_keys(
        (s.canonical_key for s in qtbj), expected_qtbj_keys(),
    )
    smth_missing, smth_extra = diff_keys(
        (e.canonical_key for e in smth), expected_smth_keys(),
    )

    payload = {
        "version": "2",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "qtbj_section_count": len(qtbj),
            "smth_entry_count": len(smth),
            "shensha_entry_count": len(shensha),
            "geju_entry_count": len(geju),
            "liuqin_entry_count": len(liuqin),
            "appearance_entry_count": len(appearance),
            "concept_entry_count": len(concept),
            "theory_entry_count": len(theory),
            "qtbj_missing_keys": qtbj_missing,
            "qtbj_extra_keys": qtbj_extra,
            "smth_missing_keys": smth_missing,
            "smth_extra_keys": smth_extra,
        },
        "qtbj_sections": [asdict(s) for s in qtbj],
        "smth_entries": [asdict(e) for e in smth],
        "shensha_entries": [asdict(e) for e in shensha],
        "geju_entries": [asdict(e) for e in geju],
        "liuqin_entries": [asdict(e) for e in liuqin],
        "appearance_entries": [asdict(e) for e in appearance],
        "concept_entries": [asdict(e) for e in concept],
        "theory_entries": [asdict(e) for e in theory],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("wrote %s", args.out)
    logger.info("QTBJ: %d found, %d missing, %d extra",
                len(qtbj), len(qtbj_missing), len(qtbj_extra))
    logger.info("SMTH: %d found, %d missing, %d extra",
                len(smth), len(smth_missing), len(smth_extra))
    if qtbj_missing:
        logger.warning("QTBJ missing keys (first 10): %s", qtbj_missing[:10])
    if smth_missing:
        logger.warning("SMTH missing keys (first 10): %s", smth_missing[:10])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
