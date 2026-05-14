from paipan.force import compute_force
from paipan.li_liang import (
    THRESHOLD_JI_QIANG,
    THRESHOLD_JI_RUO,
    THRESHOLD_SHEN_QIANG,
    THRESHOLD_ZHONG_HE,
    _classify_day_strength,
)


def test_force_returns_ten_gods_scores():
    paipan = {
        "year": {"gan": "癸", "zhi": "巳"},
        "month": {"gan": "甲", "zhi": "子"},
        "day":   {"gan": "丁", "zhi": "酉"},
        "hour":  {"gan": "甲", "zhi": "辰"},
    }
    r = compute_force(paipan, day_gan="丁")
    for key in ("比肩","劫财","食神","伤官","偏财","正财","七杀","正官","偏印","正印"):
        assert key in r
        assert isinstance(r[key], (int, float))


def test_force_sum_not_zero():
    paipan = {
        "year": {"gan": "癸", "zhi": "巳"},
        "month": {"gan": "甲", "zhi": "子"},
        "day":   {"gan": "丁", "zhi": "酉"},
        "hour":  {"gan": "甲", "zhi": "辰"},
    }
    r = compute_force(paipan, day_gan="丁")
    assert sum(r.values()) > 0


def test_day_strength_ji_qiang_at_boundary():
    """same_ratio >= THRESHOLD_JI_QIANG -> 极强."""
    assert _classify_day_strength(THRESHOLD_JI_QIANG) == "极强"
    assert _classify_day_strength(THRESHOLD_JI_QIANG + 0.01) == "极强"
    assert _classify_day_strength(1.0) == "极强"


def test_day_strength_shen_qiang_zone():
    """THRESHOLD_SHEN_QIANG <= same_ratio < THRESHOLD_JI_QIANG -> 身强."""
    assert _classify_day_strength(THRESHOLD_SHEN_QIANG) == "身强"
    assert _classify_day_strength(0.65) == "身强"
    assert _classify_day_strength(THRESHOLD_JI_QIANG - 0.01) == "身强"


def test_day_strength_zhong_he_zone():
    """THRESHOLD_ZHONG_HE <= same_ratio < THRESHOLD_SHEN_QIANG -> 中和."""
    assert _classify_day_strength(THRESHOLD_ZHONG_HE) == "中和"
    assert _classify_day_strength(0.42) == "中和"
    assert _classify_day_strength(THRESHOLD_SHEN_QIANG - 0.01) == "中和"


def test_day_strength_shen_ruo_zone():
    """THRESHOLD_JI_RUO <= same_ratio < THRESHOLD_ZHONG_HE -> 身弱."""
    assert _classify_day_strength(THRESHOLD_JI_RUO) == "身弱"
    assert _classify_day_strength(0.25) == "身弱"
    assert _classify_day_strength(THRESHOLD_ZHONG_HE - 0.01) == "身弱"


def test_day_strength_ji_ruo_below_boundary():
    """same_ratio < THRESHOLD_JI_RUO -> 极弱."""
    assert _classify_day_strength(THRESHOLD_JI_RUO - 0.01) == "极弱"
    assert _classify_day_strength(0.05) == "极弱"
    assert _classify_day_strength(0.0) == "极弱"
