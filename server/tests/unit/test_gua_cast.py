"""gua_cast: 梅花易数·时间起卦 pure function. NOTE: archive/server-mvp/gua.js."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.gua_cast import cast_gua, GUA64, _hour_to_zhi_index, _mod


def test_gua64_loaded_with_64_entries():
    assert len(GUA64) == 64
    first = GUA64[0]
    for k in ("id", "name", "symbol", "upper", "lower", "guaci", "daxiang"):
        assert k in first


@pytest.mark.parametrize("h,expected", [
    (0, 1), (23, 1),    # 子时跨日
    (1, 2), (2, 2),     # 丑
    (3, 3), (4, 3),     # 寅
    (11, 7), (12, 7),   # 午
    (21, 12), (22, 12), # 亥
])
def test_hour_to_zhi_index(h, expected):
    assert _hour_to_zhi_index(h) == expected


def test_mod_returns_in_range():
    assert _mod(8, 8) == 8
    assert _mod(9, 8) == 1
    assert _mod(0, 8) == 8


def test_cast_gua_deterministic_for_fixed_timestamp():
    """Same input -> same output (algorithm is pure)."""
    at = datetime(2026, 4, 18, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    g1 = cast_gua(at)
    g2 = cast_gua(at)
    assert g1 == g2


def test_cast_gua_returns_required_keys():
    at = datetime(2026, 4, 18, 14, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    g = cast_gua(at)
    for k in ("id", "name", "symbol", "upper", "lower", "guaci", "daxiang",
              "dongyao", "drawn_at", "source"):
        assert k in g
    assert 1 <= g["dongyao"] <= 6
    assert g["upper"] in {"乾", "兑", "离", "震", "巽", "坎", "艮", "坤"}
    assert g["lower"] in {"乾", "兑", "离", "震", "巽", "坎", "艮", "坤"}
    src = g["source"]
    assert {"yearGz", "yearZhi", "lunarMonth", "lunarDay", "hourZhiIdx",
            "sumUpper", "sumLower", "formula"}.issubset(src.keys())


def test_cast_gua_zi_hour_crosses_midnight():
    """23:00 should be 子 (idx=1) just like 00:00 -- both produce dongyao based on hourZhiIdx=1."""
    at_2300 = datetime(2026, 4, 18, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    g = cast_gua(at_2300)
    assert g["source"]["hourZhiIdx"] == 1


def test_combo_index_covers_all_64_trigram_pairs():
    """All 8×8 trigram combinations must map to a unique gua id (no dups, no gaps).

    Caught a real data bug in MVP: 鼎 (id=50) had wrong upper/lower duplicating
    家人 (id=37) and leaving (离, 巽) unmapped → live RuntimeError path.
    """
    from app.services.gua_cast import COMBO_INDEX, GUA64, TRIGRAM_NAMES
    assert len(COMBO_INDEX) == 64
    # Every combo present
    for u_idx in range(1, 9):
        for l_idx in range(1, 9):
            assert COMBO_INDEX.get(u_idx * 10 + l_idx) is not None, \
                f"missing combo {TRIGRAM_NAMES[u_idx-1]}/{TRIGRAM_NAMES[l_idx-1]}"
    # No duplicate ids in COMBO_INDEX values
    assert len(set(COMBO_INDEX.values())) == 64
    # All 64 GUA64 ids reachable
    assert {g["id"] for g in GUA64} == set(COMBO_INDEX.values())
