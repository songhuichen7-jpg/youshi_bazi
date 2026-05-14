"""# NOTE: port of archive/paipan-engine/src/ming/heKe.js:1-139.

天干合 / 地支冲合三合三会检测. Port of paipan-engine/src/ming/heKe.js.

Node exports (every one ported here):
    GAN_HE, ZHI_LIU_HE, ZHI_CHONG_PAIRS, SAN_HE_JU, SAN_HUI,
    findGanHe      → find_gan_he
    findZhiRelations → find_zhi_relations
    isChong        → is_chong
    isGanHe        → is_gan_he

All table shapes and return-dict keys mirror Node byte-for-byte (Chinese keys
like ``a``/``b``/``idx_a``/``idx_b``/``wuxing``/``zhi``/``type``/``dir``
preserved verbatim).
"""
from __future__ import annotations

from typing import Optional

# NOTE: ming/heKe.js:22-28  天干五合 (双向键覆盖)
GAN_HE: dict[str, str] = {
    "甲己": "土", "己甲": "土",
    "乙庚": "金", "庚乙": "金",
    "丙辛": "水", "辛丙": "水",
    "丁壬": "木", "壬丁": "木",
    "戊癸": "火", "癸戊": "火",
}

# NOTE: ming/heKe.js:30-37  地支六合 (午未不化 → None)
ZHI_LIU_HE: dict[str, Optional[str]] = {
    "子丑": "土", "丑子": "土",
    "寅亥": "木", "亥寅": "木",
    "卯戌": "火", "戌卯": "火",
    "辰酉": "金", "酉辰": "金",
    "巳申": "水", "申巳": "水",
    "午未": None, "未午": None,  # 午未合日月，不化
}

# NOTE: ming/heKe.js:39-41  地支六冲
ZHI_CHONG_PAIRS: list[list[str]] = [
    ["子", "午"], ["丑", "未"], ["寅", "申"],
    ["卯", "酉"], ["辰", "戌"], ["巳", "亥"],
]

# NOTE: ming/heKe.js:43-48  三合局 (main = 中气支)
SAN_HE_JU: list[dict] = [
    {"zhi": ["申", "子", "辰"], "wx": "水", "main": "子"},
    {"zhi": ["亥", "卯", "未"], "wx": "木", "main": "卯"},
    {"zhi": ["寅", "午", "戌"], "wx": "火", "main": "午"},
    {"zhi": ["巳", "酉", "丑"], "wx": "金", "main": "酉"},
]

# NOTE: ming/heKe.js:50-55  三会方
SAN_HUI: list[dict] = [
    {"zhi": ["亥", "子", "丑"], "wx": "水", "dir": "北"},
    {"zhi": ["寅", "卯", "辰"], "wx": "木", "dir": "东"},
    {"zhi": ["巳", "午", "未"], "wx": "火", "dir": "南"},
    {"zhi": ["申", "酉", "戌"], "wx": "金", "dir": "西"},
]


# NOTE: ming/heKe.js:62-77
def find_gan_he(gans: list[str]) -> list[dict]:
    """在给定的天干数组里找所有天干合。

    Returns a list of ``{a, b, idx_a, idx_b, wuxing}`` dicts (Node-shape).
    """
    results: list[dict] = []
    for i in range(len(gans)):
        for j in range(i + 1, len(gans)):
            key = gans[i] + gans[j]
            if GAN_HE.get(key) is not None:
                results.append({
                    "a": gans[i], "b": gans[j],
                    "idx_a": i, "idx_b": j,
                    "wuxing": GAN_HE[key],
                })
    return results


# NOTE: ming/heKe.js:83-124
def find_zhi_relations(zhis: list[str]) -> dict:
    """在地支数组里找六合、六冲、三合、三会、半合."""
    liu_he: list[dict] = []
    chong: list[dict] = []
    san_he: list[dict] = []
    ban_he: list[dict] = []
    san_hui: list[dict] = []

    # NOTE: ming/heKe.js:91-103  六合 / 六冲
    for i in range(len(zhis)):
        for j in range(i + 1, len(zhis)):
            k = zhis[i] + zhis[j]
            if k in ZHI_LIU_HE:
                liu_he.append({
                    "a": zhis[i], "b": zhis[j],
                    "idx_a": i, "idx_b": j,
                    "wuxing": ZHI_LIU_HE[k],
                })
            for p, q in ZHI_CHONG_PAIRS:
                if (zhis[i] == p and zhis[j] == q) or (zhis[i] == q and zhis[j] == p):
                    chong.append({
                        "a": zhis[i], "b": zhis[j],
                        "idx_a": i, "idx_b": j,
                    })

    # NOTE: ming/heKe.js:106-113  三合 / 半合
    for ju in SAN_HE_JU:
        matched = [z for z in ju["zhi"] if z in zhis]
        if len(matched) == 3:
            san_he.append({"zhi": matched, "wuxing": ju["wx"], "type": "full"})
        elif len(matched) == 2 and ju["main"] in matched:
            ban_he.append({"zhi": matched, "wuxing": ju["wx"]})

    # NOTE: ming/heKe.js:116-121  三会
    for hui in SAN_HUI:
        matched = [z for z in hui["zhi"] if z in zhis]
        if len(matched) == 3:
            san_hui.append({"zhi": matched, "wuxing": hui["wx"], "dir": hui["dir"]})

    return {
        "liuHe": liu_he,
        "chong": chong,
        "sanHe": san_he,
        "banHe": ban_he,
        "sanHui": san_hui,
    }


def analyze_relations(zhis: list[str]) -> dict:
    """Port-friendly wrapper for Plan 7.1's analyzer API.

    JS ``heKe.js`` exports the richer ``findZhiRelations`` result; Plan 7.2 now
    passes the full JS shape through to downstream consumers.
    """
    return find_zhi_relations(zhis)


# NOTE: ming/heKe.js:127-129
def is_chong(a: str, b: str) -> bool:
    """判断两地支是否冲."""
    return any((a == p and b == q) or (a == q and b == p) for p, q in ZHI_CHONG_PAIRS)


# NOTE: ming/heKe.js:132-134
def is_gan_he(a: str, b: str) -> bool:
    """判断两天干是否合."""
    return (a + b) in GAN_HE
