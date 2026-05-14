"""LLM display pass for chart classics.

Retrieval2 finds source anchors. This module turns those anchors into the
short, readable "古籍旁证" cards shown in the UI, while keeping the original
retrieved text available for provenance.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Sequence

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 75.0

# Cache schema version — single source of truth for both the API endpoint
# (writes the row) and the chat injector (reads the row). Bump together when
# PersonaQuote / VerdictQuote shape changes, or when validation rules relax
# enough that previously-cached null rows would now succeed.
CLASSICS_CACHE_VERSION = "v12"

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


async def chat_once_with_fallback(**kwargs):
    from app.llm.client import chat_once_with_fallback as _chat_once_with_fallback

    return await _chat_once_with_fallback(**kwargs)


def _clean_text(value: Any, *, max_len: int = 260) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text[:max_len].strip()


# OCR / 古籍异体字归一组。Wikisource 扫描 OCR 三命通会等古籍中很常见的
# 字符变体, zhconv 不覆盖。归一到组内首字 (canonical), 让 LLM 在"修正
# 错字"输出时不破坏 provenance 校验。每组都是视觉相似但 zhconv 不识别,
# 而 LLM 几乎总会"修正"成现代标准字形的字符对。
#
# 已验证存在于 corpus (server/var/retrieval2/claims.jsonl), 按频次排序:
#   㑹 → 会   (277x)   㓙 → 凶   (258x)
#   㐫 → 凶   (220x)   㸔 → 看   (179x)
#   岁 → 歳   (125x)   湏 → 须   (80x)
#   𤣥 → 玄   (77x)    㣲 → 微   (58x)
#   䘮 → 丧   (56x)    㓜 → 幼   (34x)
#   㫁 → 断   (34x)    㵼 → 泻   (8x)
#   黒 → 黑   (~10x)   逄 → 逢   (~30x)
#   㷔 → 焰   (~5x)    㓕 → 灭   (~14x)
#   煞 → 杀   (单独由 _compact_for_match 处理, 不在此表)
#
# 已知 LLM "纠正"行为: 巳/已/己 三字视觉极接近, 任意混用 — 单独成组。
# 注: 此表不必穷举 — `_quote_punctuate_drift_ratio` 在加标点后处理处对
# 残余少数变体提供宽容 (允许 ≤8% 字符差); 这里只覆盖主流高频组合, 把
# **provenance 阶段** 的拒收率压到接近零。
_OCR_FOLD_GROUPS: tuple[tuple[str, str], ...] = (
    ("已", "巳"),
    ("已", "己"),
    ("须", "湏"),
    ("凶", "㐫"),
    ("凶", "㓙"),
    ("看", "㸔"),
    ("会", "㑹"),
    ("岁", "歳"),
    ("玄", "𤣥"),
    ("微", "㣲"),
    ("丧", "䘮"),
    ("幼", "㓜"),
    ("断", "㫁"),
    ("泻", "㵼"),
    ("黑", "黒"),
    ("逢", "逄"),
    ("焰", "㷔"),
    ("灭", "㓕"),
)


def _compact_for_match(value: Any) -> str:
    """Strip everything except Han chars and 繁→简 fold so the quote
    membership check works regardless of variant character forms.

    Without 繁→简, an LLM that "corrects" 嵗 → 岁, 實 → 实, 見 → 见 in its
    polished quote would fail the substring check against the raw 繁体
    corpus and the polished item would be silently dropped to a raw
    fallback (which has no plain / match), losing the explanatory text.

    Also folds OCR-confusable groups (`巳/已/己` etc.) — these are not 繁简
    variants but the source 古籍 corpus is OCR'd from Wikisource scans
    where they are routinely swapped. LLMs trying to "fix typos" in the
    output trigger false-positive provenance failures otherwise.
    """
    import zhconv
    text = zhconv.convert(str(value or ""), "zh-hans").replace("煞", "杀")
    for canonical, alias in _OCR_FOLD_GROUPS:
        text = text.replace(alias, canonical)
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def _to_simplified(text: str) -> str:
    """繁体→简体规范化, 用于 quote / plain / fit_note 等用户面字段。

    保留'煞'不替换（命理术语，与"杀"含义微妙不同；古文 corpus 用'煞'）。
    标点统一保留。

    不要在 _quote_belongs_to_raw 校验前调用 — 那里需要原始字符以与
    raw_text 做精确比对。这个 helper 在 polish output 阶段应用，校验
    通过后再做 display normalization。"""
    if not text:
        return ""
    import zhconv
    return zhconv.convert(text, "zh-hans")


_ELLIPSIS_RE = re.compile(r"…+|\.{3,}")


def _quote_belongs_to_raw(quote: str, raw_text: str) -> bool:
    """True iff every ellipsis-delimited segment of the quote is a substring
    of the raw text (after stripping non-Chinese characters).

    The polisher prompt allows the LLM to "delete unrelated neighbouring
    sentences from the same paragraph", which some models (notably MiMo)
    realise as multi-segment quotes joined by …… ellipses. A naive single-
    substring check would reject these legitimate excerpts and force the
    panel into raw fallback. Splitting on the ellipsis recovers them while
    still rejecting any segment the LLM hallucinated."""
    compact_raw = _compact_for_match(raw_text)
    if not compact_raw:
        return False
    segments = [seg for seg in _ELLIPSIS_RE.split(quote) if seg.strip()]
    if not segments:
        return False
    for seg in segments:
        compact_seg = _compact_for_match(seg)
        if not compact_seg or compact_seg not in compact_raw:
            return False
    return True


def _strip_fence(text: str) -> str:
    s = (text or "").strip()
    m = _FENCE_RE.search(s)
    return (m.group(1) if m else s).strip()


def _normalize_raw_hits(hits: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for hit in hits:
        text = str(hit.get("text") or "").strip()
        if not text:
            continue
        item = dict(hit)
        item["text"] = text
        item["chars"] = int(item.get("chars") or len(text))
        out.append(item)
    return out


def _pillar_parts(chart: dict[str, Any]) -> tuple[str, str]:
    p = chart.get("PAIPAN") or chart
    sizhu = p.get("sizhu") or {}
    day = str(sizhu.get("day") or p.get("rizhu") or "")
    month = str(sizhu.get("month") or "")
    return (day[:1] if day else "", month[1:2] if len(month) >= 2 else "")


from app.retrieval2.chart_facts import PILLAR_LABELS as _PILLAR_LABELS
from app.retrieval2.chart_facts import ten_god_facts as _ten_god_facts


def _chart_summary(chart: dict[str, Any]) -> str:
    p = chart.get("PAIPAN") or chart
    sizhu = p.get("sizhu") or {}
    stems = []
    branches = []
    for label, key in _PILLAR_LABELS:
        pillar = str(sizhu.get(key) or "")
        if pillar:
            stems.append(f"{label}{pillar[:1]}")
        if len(pillar) >= 2:
            branches.append(f"{label}{pillar[1:2]}")
    parts = [
        f"四柱：年{sizhu.get('year', '')} 月{sizhu.get('month', '')} 日{sizhu.get('day', '')} 时{sizhu.get('hour', '')}",
        f"盘面天干：{'、'.join(stems)}（只有这些可称透干）" if stems else "",
        f"盘面地支：{'、'.join(branches)}（地支/藏干不可说成透干）" if branches else "",
        f"日主：{p.get('rizhu', '')}",
        f"格局：{p.get('geju', '')}",
        f"强弱：{p.get('dayStrength', '')}",
        f"用神：{p.get('yongshen', '')}",
    ]
    parts = [part for part in parts if part.split("：", 1)[-1]]
    facts = _ten_god_facts(chart)
    if facts:
        parts.append("【结构事实表 — 必须严格遵循，不得改写】\n  " + "\n  ".join(facts))
    return "\n".join(parts)


def _format_hits(hits: Sequence[dict[str, Any]]) -> str:
    """格式化候选列表 (verdict pool 用)。同 _format_persona_hits 一样
    转简体再发给 LLM；provenance 校验有双向归一不受影响。"""
    import zhconv
    lines: list[str] = []
    for i, hit in enumerate(hits):
        raw = str(hit.get("text") or "").replace("\n", " ").strip()
        text = zhconv.convert(raw, "zh-hans")
        if len(text) > 260:
            text = text[:260] + "…"
        lines.append(
            f"[{i}] {hit.get('source', '')} · {hit.get('scope', '')}\n"
            f"原文锚点：{text}"
        )
    return "\n\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# Persona (Pool A) — picture portrait
# ─────────────────────────────────────────────────────────────────────────

_PERSONA_SYSTEM = """你是八字"古书定调·画像"的编辑器。
检索系统已经从《滴天髓·性情》《子平真诠·论性情》《渊海子平·性情》《三命通会·论X日生人》等性情/论性情类章节里筛出了若干候选；候选已带 tier 标记 (case=具体命例命中本盘日干月支；general=与本盘日干或主格局相关的论文段落)。

你的任务：从候选里挑**一段**最贴本盘的输出 JSON。以下哪条候选讨论了本盘的日干 / 月令 / 主格局 / 用神 任何一项，就挑它 — 不要因为"不完美"而放弃。

输出格式：
{"id":"<候选编号>","quote":"...","plain":"...","fit_note":"...","tier":"case"|"general","book":"...","chapter":"...","section":"..."}

quote：
- 逐字摘自候选原文，可截关键句、删同段无关邻句
- **必须加中文标点**（古书原文常无断句；按文意加逗号、顿号、句号）
- 长度上限 400 字；下限不限，短判语（哪怕 15-30 字）也照样选
- 不要改字 — 包括"修正"看似的错字

plain：
- 给普通人读的白话翻译，60-200 字
- 用日常语言；如果用了"七杀"、"伤官"、"印"、"日主"等术语，**在术语后用括号或一句话解释**：例如"七杀（来自外部的压力或挑战）"、"日主（你这个人）"、"印（守护、滋养你的力量）"
- 不是简单复述古文，而是讲清楚"这种命格的人是什么样、为什么、要注意什么"

fit_note：≤30 字，引用结构事实。例："日干甲、月令丑、印格中和"。

何时输出 {"id":null}：**仅当所有候选都与本盘完全无关**（不同日干家族 + 不同格局 + 议题完全无关）。
**不要因为翻译有难度、标点不好加、白话不好写、长度难控制就放弃。** 这些是格式问题，不是匹配问题。
任何一条候选讨论了本盘的日干 / 月令 / 格局 / 用神 / 性情 — 就挑它。

只输出 JSON，不要解释，不要 markdown fence。"""


def _format_persona_hits(hits: Sequence[dict[str, Any]]) -> str:
    """格式化候选列表给 LLM 看。每条带 tier 标签。

    候选原文通过 zhconv 转简体再展示 — fast tier 模型对繁体古文+无标点
    的处理能力有限。Provenance 校验 (_quote_belongs_to_raw) 用
    _compact_for_match 做双向归一比对，不受展示形态影响。"""
    import zhconv
    lines: list[str] = []
    for i, hit in enumerate(hits):
        raw = str(hit.get("text") or "").replace("\n", " ").strip()
        text = zhconv.convert(raw, "zh-hans")
        if len(text) > 360:
            text = text[:360] + "…"
        tier = hit.get("_tier", "?")
        lines.append(
            f"[{i}] tier={tier} · {hit.get('source', '')} · {hit.get('scope', '')}\n"
            f"原文：{text}"
        )
    return "\n\n".join(lines)


def _build_persona_messages(
    chart: dict[str, Any], hits: Sequence[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _PERSONA_SYSTEM},
        {
            "role": "user",
            "content": (
                f"【命盘】\n{_chart_summary(chart)}\n\n"
                f"【候选锚点】\n{_format_persona_hits(hits)}\n\n"
                f"请从候选里挑最贴的一段，输出 JSON。"
            ),
        },
    ]


def _parse_persona_item(
    text: str, raw_hits: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    """解析 LLM 输出 — 成功返回 dict (PersonaQuote 形)，失败/空选返回 None。"""
    try:
        data = json.loads(_strip_fence(text))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    raw_id = data.get("id")
    if raw_id is None:
        return None
    try:
        idx = int(str(raw_id).strip())
    except (ValueError, TypeError):
        return None
    if idx < 0 or idx >= len(raw_hits):
        return None
    raw = raw_hits[idx]

    quote = _clean_text(data.get("quote"), max_len=420)
    if not quote or not _quote_belongs_to_raw(quote, str(raw.get("text") or "")):
        return None
    # 不在这里拒绝无标点的 quote — 古籍原文常无断句而 LLM 在 temp=0 下
    # 倾向直接照抄不加, 强拒收会把"内容正确但格式不达标"打成空态。
    # 标点交由 _polish_persona 调一次 fast tier 后处理补齐, 不行再降级
    # 显示原文 (体验仍优于空态)。
    if not _verdict_passes_extreme_check(quote):
        return None

    plain = _clean_text(data.get("plain"), max_len=320)
    fit_note = _clean_text(data.get("fit_note"), max_len=60)
    tier = str(data.get("tier") or "").strip()
    if tier not in {"case", "general"}:
        tier = str(raw.get("_tier") or "general")
    if tier not in {"case", "general"}:
        tier = "general"
    if not plain or not fit_note:
        return None

    return {
        "quote": _to_simplified(quote),
        "plain": _to_simplified(plain),
        "book": _to_simplified(str(data.get("book") or raw.get("source") or "")),
        "chapter": _to_simplified(str(data.get("chapter") or raw.get("scope") or "")),
        "section": _to_simplified(_clean_text(data.get("section"), max_len=80)) or None,
        "tier": tier,
        "fit_note": _to_simplified(fit_note),
    }


async def _polish_persona(
    chart: dict[str, Any], raw_hits: Sequence[dict[str, Any]], timeout_seconds: float,
) -> dict[str, Any] | None:
    """Run persona polish with one retry on null. LLM at temperature 0
    is mostly deterministic but candidates can hit edge cases — a single
    retry catches "LLM played it safe" without doubling cost in the
    common path."""
    if not raw_hits:
        return None
    for attempt in range(2):  # 第二次是 retry, 用于打破 null 落点
        try:
            text, _model = await asyncio.wait_for(
                chat_once_with_fallback(
                    messages=_build_persona_messages(chart, raw_hits),
                    tier="primary",
                    temperature=0.0 if attempt == 0 else 0.4,
                    max_tokens=2000,
                    disable_thinking=True,
                ),
                timeout=timeout_seconds,
            )
            parsed = _parse_persona_item(text, raw_hits)
            if parsed is not None:
                # 后处理: 无标点的 quote 走 fast tier 补标点 (字未改才采用)
                parsed["quote"] = await _punctuate_quote_via_llm(parsed["quote"])
                return parsed
            # null on attempt 0 — retry once with higher temperature
            # (sometimes LLM gets "stuck" on safe answer at temp=0)
            logger.info(
                "persona polish attempt %d returned null — retrying with higher temperature",
                attempt,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("persona polish attempt %d failed: %r", attempt, exc)
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────
# Verdict (Pool B) — short punchline
# ─────────────────────────────────────────────────────────────────────────

_VERDICT_SYSTEM = """你是八字"古书定调·定语"的编辑器。
检索系统从《子平真诠·论用神成败》《渊海子平·喜忌歌》《三命通会·论命格高下》等章节挑出若干判文锚点。

你的任务：从候选里**挑一句**最对得上本盘的格局成败 / 用神得力短判语，输出 JSON。

匹配宽度：
- 完全字面一致最理想（"甲用申官" 直接讲本盘）
- **同型推断也算贴合** — 候选写"乙用酉杀，辛逢丁制"而本盘是"甲用申杀，丁火制杀" — 都是金类七杀 + 火类制化，属同一格局类型，仍可选
- 类似 "杀印相生"、"伤官配印"、"财官印俱全" 这种格局判语，本盘对得上格局名时就算合规
- 候选若是泛论（不针对具体日干 / 格局组合），也可以选只要它讨论的现象与本盘一致

quote 规则：
- quote 必须**逐字摘自候选原文**；不可改字（繁→简由系统统一处理）
- **必须给 quote 加标点** — 古籍原文常无断句符号；按文意加上正确的中文标点。**不加标点视为格式错误**
- quote 长度 ≤ 50 字（不算标点）
- 如果合适的判语只有 10-20 字，照原样保留；不要硬凑

凶词处理：
- 含"贫"、"夭"、"刑"、"克妻"、"早卒" 等极端凶词若 **单独** 出现 → 整段舍弃
- 极端凶词与制化办法同段时 — 仍需在 quote 里把制化语境一同截入，否则舍弃
- 中性技术词（"伤官""七杀""制化""化煞""杀印相生""偏印夺食"）不算凶词

**何时输出 {"id":null}**：仅当所有候选都与本盘**议题性无关**（不讨论本盘的格局、用神、喜忌方向）才返回 null。**不要因为字面不完全一致、长度难控制、或标点难加就先放弃** — 只要某条候选讲的现象与本盘对得上（即使日干/月支差一格），就要挑出来。

只输出 JSON：
{"id":"<候选编号>","quote":"...","book":"...","chapter":"..."}

或：{"id":null}"""


def _build_verdict_messages(
    chart: dict[str, Any], hits: Sequence[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _VERDICT_SYSTEM},
        {
            "role": "user",
            "content": (
                f"【命盘】\n{_chart_summary(chart)}\n\n"
                f"【候选判文锚点】\n{_format_hits(hits)}\n\n"
                f"请挑一句最贴的，输出 JSON。"
            ),
        },
    ]


# 注意: 不含 "伤" — 在子平命理里 "伤" 几乎全是 "伤官" 这个十神技术词，
# 收入 _EXTREME_WORDS 会把 "伤官配印则贵" 这类正面判语误杀。
# 真正的极端凶词靠 "刑/克妻/克夫/夭/贫/早卒/短寿" 已经足够覆盖。
_EXTREME_WORDS = ("贫", "夭", "刑", "克妻", "克夫", "早卒", "短寿")
_REMEDY_WORDS = ("制", "化", "救", "通", "调", "扶", "抑")


def _verdict_passes_extreme_check(quote: str) -> bool:
    """极端凶词单独出现 (没有制化语境) 时拒绝。"""
    if not any(w in quote for w in _EXTREME_WORDS):
        return True
    return any(w in quote for w in _REMEDY_WORDS)


# 中文标点符号集 — quote 必须含至少 1 个其中之一才算合规。空格不算。
_CN_PUNCTUATION_RE = re.compile(r"[，。、；：？！,.;:?!“”\"'…—…]")


def _quote_has_punctuation(quote: str, *, min_chars: int = 20) -> bool:
    """quote 长于 ``min_chars`` 时是否已含中文标点。仅作判断, 不再用于拒收
    (拒收策略已撤销 — 现在改成无标点时调 LLM 后处理补)。"""
    if not quote or len(quote) <= min_chars:
        return True
    return bool(_CN_PUNCTUATION_RE.search(quote))


_PUNCTUATE_SYSTEM = (
    "你是古籍标点编辑。给输入的中文古文加上中文标点（逗号、句号、顿号），"
    "**一字不改, 一字不删, 一字不增**。仅输出加好标点的文本本身, 不要解释, "
    "不要 markdown, 不要前后缀。"
)


def _strip_punctuation_for_compare(text: str) -> str:
    """剥离标点 + 空白 + 繁简 + OCR 变体, 用于校验 LLM 后处理是否仅添加
    标点而未实质改字。

    复用 ``_compact_for_match`` — 它已对 ``_OCR_FOLD_GROUPS`` 列出的常见
    变体做了折叠。但古籍 OCR 变体面广（㓙/凶, 㷔/焰, 𪸩/荧, 㓕/灭, 黒/黑,
    逄/逢, 𢔽 …），任何静态表都难穷举。所以这个函数只剥标点并粗归一,
    最终的"等价"判定走 ``_quote_punctuate_drift_ratio`` (字符差异比例)。"""
    return _compact_for_match(text)


def _quote_punctuate_drift_ratio(original: str, punctuated: str) -> float:
    """估算 LLM 加标点后的"非标点字符变更比例"。

    动机: ``_OCR_FOLD_GROUPS`` 是有限白名单, 古籍 OCR 变体边界很广 (㓙/㷔
    /𪸩/𢔽 这种字符都会出现); 严格 char-equality 在这种边界条件下回退率
    太高 (用户体验是"无标点的连写大段"取代了"有标点的可读版本")。

    这里允许小比例字符级差异 (默认 ≤8%) — 因为加标点 fast tier LLM 的
    任务设计就是"加标点 + 顺手修明显错字", **provenance 已经在上游
    `_quote_belongs_to_raw` 那道闸校验过**, 这里只是 display 步, 不是
    correctness 步, 不必再苛刻一次。

    返回 0.0 时表示 compact 形式完全等价; 1.0 表示完全不同。"""
    a = _strip_punctuation_for_compare(original)
    b = _strip_punctuation_for_compare(punctuated)
    if not a or not b:
        return 1.0
    # SequenceMatcher.ratio = 2 * matching / (len(a) + len(b)) ∈ [0, 1]
    # ratio = 1.0 → identical;  drift = 1 - ratio
    import difflib
    return 1.0 - difflib.SequenceMatcher(None, a, b).ratio()


_MAX_PUNCTUATE_DRIFT = 0.08  # 允许最多 8% 字符不一致 (典型 OCR 修正在 1-3%)


async def _punctuate_quote_via_llm(
    quote: str, *, timeout_seconds: float = 10.0,
) -> str:
    """对无标点的 quote 调一次 fast tier LLM 加标点。

    - 仅当返回内容剥标点后等于原 quote (字符序一致) 才采用; 否则回退原文。
    - LLM 调用任何异常 → 回退原文。
    - 长度 ≤20 字短 quote 不需断句, 直接返回原文。
    """
    if not quote or len(quote) <= 20 or _CN_PUNCTUATION_RE.search(quote):
        return quote
    try:
        text, _model = await asyncio.wait_for(
            chat_once_with_fallback(
                messages=[
                    {"role": "system", "content": _PUNCTUATE_SYSTEM},
                    {"role": "user", "content": quote},
                ],
                tier="fast",
                temperature=0.0,
                max_tokens=300,
                disable_thinking=True,
            ),
            timeout=timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("punctuate fallback (LLM error): %r", exc)
        return quote
    candidate = (text or "").strip()
    # 剥 fence (有时模型还是会加)
    candidate = _strip_fence(candidate)
    if not candidate:
        return quote
    drift = _quote_punctuate_drift_ratio(quote, candidate)
    if drift > _MAX_PUNCTUATE_DRIFT:
        logger.info(
            "punctuate fallback (drift %.1f%% > %.1f%%): %r → %r",
            drift * 100, _MAX_PUNCTUATE_DRIFT * 100, quote, candidate,
        )
        return quote
    return candidate


def _parse_verdict_item(
    text: str, raw_hits: Sequence[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        data = json.loads(_strip_fence(text))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    raw_id = data.get("id")
    if raw_id is None:
        return None
    try:
        idx = int(str(raw_id).strip())
    except (ValueError, TypeError):
        return None
    if idx < 0 or idx >= len(raw_hits):
        return None
    raw = raw_hits[idx]

    quote = _clean_text(data.get("quote"), max_len=80)
    if not quote or not _quote_belongs_to_raw(quote, str(raw.get("text") or "")):
        return None
    # 不拒收无标点 quote — 同 _parse_persona_item 同理, 标点补齐放在
    # _polish_verdict 后处理。
    if not _verdict_passes_extreme_check(quote):
        return None

    return {
        "quote": _to_simplified(quote),
        "book": _to_simplified(str(data.get("book") or raw.get("source") or "")),
        "chapter": _to_simplified(str(data.get("chapter") or raw.get("scope") or "")),
    }


async def _polish_verdict(
    chart: dict[str, Any], raw_hits: Sequence[dict[str, Any]], timeout_seconds: float,
) -> dict[str, Any] | None:
    if not raw_hits:
        return None
    for attempt in range(2):
        try:
            text, _model = await asyncio.wait_for(
                chat_once_with_fallback(
                    messages=_build_verdict_messages(chart, raw_hits),
                    tier="fast",
                    temperature=0.0 if attempt == 0 else 0.4,
                    max_tokens=400,
                    disable_thinking=True,
                ),
                timeout=timeout_seconds,
            )
            parsed = _parse_verdict_item(text, raw_hits)
            if parsed is not None:
                parsed["quote"] = await _punctuate_quote_via_llm(parsed["quote"])
                return parsed
            logger.info(
                "verdict polish attempt %d returned null — retrying with higher temperature",
                attempt,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("verdict polish attempt %d failed: %r", attempt, exc)
            return None
    return None


# ─────────────────────────────────────────────────────────────────────────
# Public entry — parallel persona + verdict polish
# ─────────────────────────────────────────────────────────────────────────


def _annotate_persona_tier(
    chart: dict[str, Any], hits: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pre-filter persona candidates with classics_persona_match and attach
    `_tier`. Drops `no-match` entries entirely."""
    from app.services.classics_persona_match import is_structural_match
    paipan = chart.get("PAIPAN") or chart
    out: list[dict[str, Any]] = []
    for hit in hits:
        text = str(hit.get("text") or "")
        tier = is_structural_match(text, paipan)
        if tier == "no-match":
            continue
        annotated = dict(hit)
        annotated["_tier"] = tier
        out.append(annotated)
    return out


async def polish_classics_for_chart(
    chart: dict[str, Any],
    persona_hits: Sequence[dict[str, Any]],
    verdict_hits: Sequence[dict[str, Any]],
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run persona + verdict polish in parallel, return final response payload.

    Returns ``{"persona": <PersonaQuote-shaped dict | None>,
              "verdict": <VerdictQuote-shaped dict | None>}``.
    """
    persona_normalized = _normalize_raw_hits(persona_hits)
    verdict_normalized = _normalize_raw_hits(verdict_hits)
    persona_annotated = _annotate_persona_tier(chart, persona_normalized)

    persona_task = asyncio.create_task(
        _polish_persona(chart, persona_annotated, timeout_seconds)
    ) if persona_annotated else None
    verdict_task = asyncio.create_task(
        _polish_verdict(chart, verdict_normalized, timeout_seconds)
    ) if verdict_normalized else None

    persona = await persona_task if persona_task else None
    verdict = await verdict_task if verdict_task else None

    return {"persona": persona, "verdict": verdict}


__all__ = ["polish_classics_for_chart", "DEFAULT_TIMEOUT_SECONDS"]
