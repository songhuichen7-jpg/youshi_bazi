"""Gan/Zhi lookup tables + wuxing sheng/ke relations.

Port of paipan-engine/src/ming/ganzhi.js.

Node exports (every one ported here):
    TIAN_GAN, DI_ZHI, GAN_WUXING, GAN_YINYANG, ZHI_WUXING, ZHI_YINYANG,
    WUXING_SHENG, WUXING_KE, generates(), overcomes(),
    DIZHI_MONTH, ZHI_CATEGORY.

Naming note: spec tests reference ``GAN``/``ZHI`` (Python convention) rather
than Node's ``TIAN_GAN``/``DI_ZHI``. Both names are exported as aliases of the
same list so either works.

``split_ganzhi`` has no Node counterpart — it is a small Python helper added
for ergonomic unpacking of two-character 干支 strings. (Node-side code indexes
strings directly: ``gz[0]``/``gz[1]``.)
"""
from __future__ import annotations

# NOTE: ming/ganzhi.js:5
TIAN_GAN: list[str] = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
# NOTE: ming/ganzhi.js:6
DI_ZHI: list[str] = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# Python-style aliases (spec tests import these names).
GAN: list[str] = TIAN_GAN
ZHI: list[str] = DI_ZHI

# NOTE: ming/ganzhi.js:9-15  天干 → 五行
GAN_WUXING: dict[str, str] = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# NOTE: ming/ganzhi.js:18-21  天干 → 阴阳
GAN_YINYANG: dict[str, str] = {
    "甲": "阳", "丙": "阳", "戊": "阳", "庚": "阳", "壬": "阳",
    "乙": "阴", "丁": "阴", "己": "阴", "辛": "阴", "癸": "阴",
}

# NOTE: ming/ganzhi.js:24-30  地支 → 五行（本气）
ZHI_WUXING: dict[str, str] = {
    "子": "水", "亥": "水",
    "寅": "木", "卯": "木",
    "巳": "火", "午": "火",
    "申": "金", "酉": "金",
    "辰": "土", "戌": "土", "丑": "土", "未": "土",
}

# NOTE: ming/ganzhi.js:33-36  地支 → 阴阳
ZHI_YINYANG: dict[str, str] = {
    "子": "阳", "寅": "阳", "辰": "阳", "午": "阳", "申": "阳", "戌": "阳",
    "丑": "阴", "卯": "阴", "巳": "阴", "未": "阴", "酉": "阴", "亥": "阴",
}

# NOTE: ming/ganzhi.js:39  五行相生
WUXING_SHENG: dict[str, str] = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}

# NOTE: ming/ganzhi.js:40  五行相克
WUXING_KE: dict[str, str] = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


# NOTE: ming/ganzhi.js:42
def generates(a: str, b: str) -> bool:
    """True iff wuxing ``a`` generates (生) wuxing ``b``."""
    return WUXING_SHENG.get(a) == b


# NOTE: ming/ganzhi.js:43
def overcomes(a: str, b: str) -> bool:
    """True iff wuxing ``a`` overcomes (克) wuxing ``b``."""
    return WUXING_KE.get(a) == b


# NOTE: ming/ganzhi.js:47-50  月令 → 对应地支（寅=1月...丑=12月）
DIZHI_MONTH: dict[str, int] = {
    "寅": 1, "卯": 2, "辰": 3, "巳": 4, "午": 5, "未": 6,
    "申": 7, "酉": 8, "戌": 9, "亥": 10, "子": 11, "丑": 12,
}

# NOTE: ming/ganzhi.js:53-57  地支分类（四仲/四孟/四库）
ZHI_CATEGORY: dict[str, str] = {
    "子": "四仲", "午": "四仲", "卯": "四仲", "酉": "四仲",
    "寅": "四孟", "申": "四孟", "巳": "四孟", "亥": "四孟",
    "辰": "四库", "戌": "四库", "丑": "四库", "未": "四库",
}


def split_ganzhi(gz: str) -> tuple[str, str]:
    """Split a two-char 干支 like '癸巳' into ('癸', '巳').

    No Node counterpart — added as a Python ergonomic helper.
    """
    if len(gz) != 2:
        raise ValueError(f"invalid ganzhi: {gz!r}")
    return gz[0], gz[1]
