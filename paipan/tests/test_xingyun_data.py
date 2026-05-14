"""Plan 7.4 — xingyun_data table structure validity."""
from __future__ import annotations

from paipan.xingyun_data import (
    GAN_HE_TABLE,
    ZHI_LIUHE_TABLE,
    SCORE_THRESHOLDS,
    YONGSHEN_WEIGHTS,
)
from paipan.xingyun import _classify_score


def test_gan_he_table_has_5_pairs():
    """5 traditional 天干五合."""
    assert len(GAN_HE_TABLE) == 5
    expected = {
        frozenset({'甲', '己'}),
        frozenset({'乙', '庚'}),
        frozenset({'丙', '辛'}),
        frozenset({'丁', '壬'}),
        frozenset({'戊', '癸'}),
    }
    assert set(GAN_HE_TABLE.keys()) == expected


def test_zhi_liuhe_table_has_6_pairs():
    """6 traditional 地支六合."""
    assert len(ZHI_LIUHE_TABLE) == 6
    expected = {
        frozenset({'子', '丑'}),
        frozenset({'寅', '亥'}),
        frozenset({'卯', '戌'}),
        frozenset({'辰', '酉'}),
        frozenset({'巳', '申'}),
        frozenset({'午', '未'}),
    }
    assert set(ZHI_LIUHE_TABLE.keys()) == expected


def test_gan_he_outputs_are_valid_wuxings():
    """Every 化出 五行 must be one of 5 元素."""
    valid = {'木', '火', '土', '金', '水'}
    for pair, wx in GAN_HE_TABLE.items():
        assert wx in valid, f'{pair} 化出 {wx!r} not a wuxing'


def test_zhi_liuhe_outputs_are_valid_wuxings():
    valid = {'木', '火', '土', '金', '水'}
    for pair, wx in ZHI_LIUHE_TABLE.items():
        assert wx in valid, f'{pair} 化出 {wx!r} not a wuxing'


def test_score_thresholds_classify_5_bins():
    """Verify _classify_score covers all 5 bins at boundaries."""
    assert _classify_score(5) == '大喜'
    assert _classify_score(4) == '大喜'
    assert _classify_score(3) == '喜'
    assert _classify_score(2) == '喜'
    assert _classify_score(1) == '平'
    assert _classify_score(0) == '平'
    assert _classify_score(-1) == '平'
    assert _classify_score(-2) == '忌'
    assert _classify_score(-3) == '忌'
    assert _classify_score(-4) == '大忌'
    assert _classify_score(-5) == '大忌'


def test_yongshen_weights_valid():
    """Plan 7.6 §4.2: YONGSHEN_WEIGHTS = [0.5, 0.3, 0.2], sum=1.0, decreasing."""
    assert YONGSHEN_WEIGHTS == [0.5, 0.3, 0.2]
    assert abs(sum(YONGSHEN_WEIGHTS) - 1.0) < 1e-9
    for i in range(1, len(YONGSHEN_WEIGHTS)):
        assert YONGSHEN_WEIGHTS[i] <= YONGSHEN_WEIGHTS[i - 1]
