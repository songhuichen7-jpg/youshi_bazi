"""十神判定. Port of paipan-engine/src/ming/shishen.js.

Rule-based derivation (matches Node source — not a lookup table):

  - 同我者 → 比劫（同五行）
      同阴阳：比肩；异阴阳：劫财
  - 我生者 → 食伤
      同阴阳：食神；异阴阳：伤官
  - 我克者 → 财
      同阴阳：偏财；异阴阳：正财
  - 克我者 → 官杀
      同阴阳：七杀；异阴阳：正官
  - 生我者 → 印
      同阴阳：偏印；异阴阳：正印

Node exports ported:
    getShiShen       → get_shi_shen
    getShiShenGroup  → get_shi_shen_group
    SHI_SHEN_PAIRS   → SHI_SHEN_PAIRS (kept as Python dict[str, list[str]])

Added (Python-only): ``SHI_SHEN_NAMES`` — the flat set of 10 names, for
test assertions and membership checks. No Node counterpart.
"""
from __future__ import annotations

from paipan.ganzhi import GAN_WUXING, GAN_YINYANG, WUXING_KE, WUXING_SHENG


# NOTE: ming/shishen.js:44-50  十神分组
SHI_SHEN_PAIRS: dict[str, list[str]] = {
    "比劫": ["比肩", "劫财"],
    "食伤": ["食神", "伤官"],
    "财": ["正财", "偏财"],
    "官杀": ["正官", "七杀"],
    "印": ["正印", "偏印"],
}

# Flat set of all 10 十神 names. No Node counterpart — added for Python ergonomics.
SHI_SHEN_NAMES: set[str] = {name for pair in SHI_SHEN_PAIRS.values() for name in pair}


# NOTE: ming/shishen.js:28-41
def get_shi_shen(day_gan: str, other_gan: str) -> str:
    """计算 ``other_gan`` 对日主 ``day_gan`` 的十神关系."""
    ri_wx = GAN_WUXING[day_gan]
    ri_yy = GAN_YINYANG[day_gan]
    g_wx = GAN_WUXING[other_gan]
    g_yy = GAN_YINYANG[other_gan]
    same_yy = ri_yy == g_yy

    # NOTE: ming/shishen.js:35
    if g_wx == ri_wx:
        return "比肩" if same_yy else "劫财"
    # NOTE: ming/shishen.js:36
    if WUXING_SHENG[ri_wx] == g_wx:
        return "食神" if same_yy else "伤官"
    # NOTE: ming/shishen.js:37
    if WUXING_KE[ri_wx] == g_wx:
        return "偏财" if same_yy else "正财"
    # NOTE: ming/shishen.js:38
    if WUXING_KE[g_wx] == ri_wx:
        return "七杀" if same_yy else "正官"
    # NOTE: ming/shishen.js:39
    if WUXING_SHENG[g_wx] == ri_wx:
        return "偏印" if same_yy else "正印"
    # NOTE: ming/shishen.js:40  — Node returns the string '未知'; ported verbatim.
    return "未知"


# NOTE: ming/shishen.js:53-58
def get_shi_shen_group(shishen: str) -> str | None:
    """Reverse-lookup: which 十神分组 does ``shishen`` belong to."""
    for k, v in SHI_SHEN_PAIRS.items():
        if shishen in v:
            return k
    return None
