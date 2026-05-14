"""梅花易数·时间起卦 -- pure function port of archive/server-mvp/gua.js.

Given a timestamp, returns the cast hexagram + 动爻 + provenance source.
Deterministic; no IO besides reading gua64.json once at module load.
"""
from __future__ import annotations

import json
import warnings
from datetime import datetime
from importlib.resources import files
from typing import Any

from lunar_python import Solar

# NOTE: gua.js:14 -- 八卦序：乾1 兑2 离3 震4 巽5 坎6 艮7 坤8
TRIGRAM_NAMES = ["乾", "兑", "离", "震", "巽", "坎", "艮", "坤"]

# NOTE: gua.js:30 -- 地支序：子1, 丑2, ..., 亥12
ZHI_INDEX = {
    "子": 1, "丑": 2, "寅": 3, "卯": 4, "辰": 5, "巳": 6,
    "午": 7, "未": 8, "申": 9, "酉": 10, "戌": 11, "亥": 12,
}


def _load_gua64() -> list[dict[str, Any]]:
    data_path = files("app.data.zhouyi").joinpath("gua64.json")
    return json.loads(data_path.read_text(encoding="utf-8"))


GUA64: list[dict[str, Any]] = _load_gua64()


# NOTE: gua.js:18-26 -- combo index keyed by upperIdx*10+lowerIdx -> gua.id
def _build_combo_index() -> dict[int, int]:
    m: dict[int, int] = {}
    seen_names: dict[int, str] = {}
    for g in GUA64:
        u = TRIGRAM_NAMES.index(g["upper"]) + 1 if g.get("upper") in TRIGRAM_NAMES else 0
        l = TRIGRAM_NAMES.index(g["lower"]) + 1 if g.get("lower") in TRIGRAM_NAMES else 0
        if u > 0 and l > 0:
            key = u * 10 + l
            if key in m:
                warnings.warn(
                    f"gua64.json: duplicate combo {g['upper']}/{g['lower']} "
                    f"({g['name']} overwrites {seen_names[key]})",
                    stacklevel=2,
                )
            m[key] = g["id"]
            seen_names[key] = g["name"]
    return m


COMBO_INDEX: dict[int, int] = _build_combo_index()


def _hour_to_zhi_index(hour: int) -> int:
    """NOTE: gua.js:33-37 -- 子时跨日：23点也算子时."""
    if hour == 23 or hour == 0:
        return 1
    return (hour + 1) // 2 + 1


def _mod(n: int, m: int) -> int:
    """NOTE: gua.js:40-43 -- 1..m mapping (0 -> m)."""
    r = n % m
    return m if r == 0 else r


def cast_gua(at: datetime) -> dict[str, Any]:
    """Cast a hexagram for the given moment.

    NOTE: gua.js:50-100. Returns dict matching the JS shape; see test for keys.
    JS used drawnAt (camelCase); Python port uses drawn_at (snake_case).

    IMPORTANT: ``at`` must represent the moment in local Chinese calendar
    time (typically Asia/Shanghai). The hour, lunar month, and lunar day are
    read directly from ``at``; passing a UTC-aware datetime will silently
    produce a wrong hexagram. Callers (e.g. conversation_gua.stream_gua)
    should convert to Asia/Shanghai before calling: at.astimezone(ZoneInfo("Asia/Shanghai")).
    """
    solar = Solar.fromYmdHms(
        at.year, at.month, at.day,
        at.hour, at.minute, at.second,
    )
    lunar = solar.getLunar()

    year_gz = lunar.getYearInGanZhi()           # e.g. "丙午"
    year_zhi = year_gz[1]
    year_zhi_idx = ZHI_INDEX.get(year_zhi, 1)

    lunar_month = abs(lunar.getMonth())          # 闰月暂按本月
    lunar_day = lunar.getDay()
    hour_zhi_idx = _hour_to_zhi_index(at.hour)

    sum_upper = year_zhi_idx + lunar_month + lunar_day
    sum_lower = sum_upper + hour_zhi_idx
    upper_idx = _mod(sum_upper, 8)
    lower_idx = _mod(sum_lower, 8)
    dongyao = _mod(sum_lower, 6)

    gua_id = COMBO_INDEX.get(upper_idx * 10 + lower_idx)
    if gua_id is None:
        raise RuntimeError(f"gua lookup failed: upper={upper_idx} lower={lower_idx}")
    gua = next(g for g in GUA64 if g["id"] == gua_id)

    upper_name = TRIGRAM_NAMES[upper_idx - 1]
    lower_name = TRIGRAM_NAMES[lower_idx - 1]
    formula = (
        f"上卦 ({year_zhi_idx}+{lunar_month}+{lunar_day})mod8 = {upper_idx} {upper_name} / "
        f"下卦 ({sum_upper}+{hour_zhi_idx})mod8 = {lower_idx} {lower_name} / "
        f"动爻 mod6 = {dongyao}"
    )

    return {
        "id": gua["id"],
        "name": gua["name"],
        "symbol": gua["symbol"],
        "upper": gua["upper"],
        "lower": gua["lower"],
        "guaci": gua["guaci"],
        "daxiang": gua["daxiang"],
        "dongyao": dongyao,
        "drawn_at": solar.toYmdHms(),
        "source": {
            "yearGz": year_gz,
            "yearZhi": year_zhi,
            "yearZhiIdx": year_zhi_idx,
            "lunarMonth": lunar_month,
            "lunarDay": lunar_day,
            "hourZhiIdx": hour_zhi_idx,
            "sumUpper": sum_upper,
            "sumLower": sum_lower,
            "formula": formula,
        },
    }
