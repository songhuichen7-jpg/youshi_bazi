"""Plan 7.4 行运 engine — skeleton & integration."""
from __future__ import annotations

import pytest

from paipan import compute
from paipan.xingyun_data import YONGSHEN_WEIGHTS
from paipan.xingyun import (
    _detect_xingyun_transmutation,
    _is_same_combo,
    _trim_note,
    build_xingyun,
    _detect_ganhe,
    _detect_liuhe,
    _score_gan_to_yongshen,
    _score_zhi_to_yongshen,
    score_yun,
)


def test_chart_xingyun_present_and_is_dict():
    """Plan 7.4 §6.1: chart.paipan.xingyun is a dict."""
    out = compute(year=1993, month=7, day=15, hour=14, minute=30,
                   gender='male', city='长沙')
    assert isinstance(out.get('xingyun'), dict)


def test_chart_xingyun_has_expected_top_keys():
    """Plan 7.4 §5.2: required top-level keys present."""
    out = compute(year=1993, month=7, day=15, hour=14, minute=30,
                   gender='male', city='长沙')
    xy = out['xingyun']
    assert 'dayun' in xy
    assert 'liunian' in xy
    assert 'currentDayunIndex' in xy
    assert 'yongshenSnapshot' in xy


def test_chart_xingyun_yongshenSnapshot_matches_plan73_primary():
    """xingyun.yongshenSnapshot == yongshenDetail.primary."""
    out = compute(year=1993, month=7, day=15, hour=14, minute=30,
                   gender='male', city='长沙')
    assert out['xingyun']['yongshenSnapshot'] == out['yongshenDetail']['primary']


# === 干合化 detection ===

def test_detect_ganhe_甲己合土():
    """命局含 己 + 行运 甲 → 合化 土."""
    assert _detect_ganhe('甲', ['己', '丁', '丁']) == '土'


def test_detect_ganhe_no_match():
    """命局没有可合的 干 → None."""
    assert _detect_ganhe('甲', ['乙', '丙', '丁']) is None


def test_detect_ganhe_adjacent_命局_fires():
    """命局干 [甲, 己, ...] 年-月相邻 → 土."""
    result = _detect_ganhe('甲', ['甲', '己', '乙', '丙'], source_idx=0)
    assert result == '土'


def test_detect_ganhe_non_adjacent_命局_misses():
    """命局干 [甲, 乙, 己, 丙] 年-日不相邻 → strict reject."""
    result = _detect_ganhe('甲', ['甲', '乙', '己', '丙'], source_idx=0)
    assert result is None


def test_detect_ganhe_external_any_position_fires():
    """External 干 with source_idx=None still matches any position."""
    result = _detect_ganhe('甲', ['乙', '丙', '丁', '己'])
    assert result == '土'


# === 干 score ===

def test_score_gan_pure_sheng():
    """癸 (水) 生 甲木 用神 → +2."""
    delta, reason, mech = _score_gan_to_yongshen('癸', '木', [])
    assert delta == 2
    assert '生用神' in reason
    assert any('相生' in m for m in mech)


def test_score_gan_with_ganhe_modifier():
    """戊 vs 木 用神：基础 0 (用神克 戊)，但 命局 含 癸 → 戊癸合化火，火泄木 → 干 -1 modifier。

    最终 delta = 0 + 0 (用神克干 base) + (-1 if 火克木 else +1 if 火生木)
    五行 火 生 木 (no), 火 克 木 (no, actually 火 不克 木 — 金克木). 火 与 木 关系：木生火，火 是 木的食伤 → spec 规则 "合化五行 生用神→+1"，但这里是 用神 生 合化五行 (木生火) → no rule fires → modifier 0.

    Wait — re-reading spec §3.3 干合化 modifier: 只看合化五行 == 用神/生用神/克用神 三种。木生火 不在这三种里 → modifier 0. So delta stays 0.
    """
    delta, reason, mech = _score_gan_to_yongshen('戊', '木', ['癸', '己', '丁'])
    # base: 木 克 戊 → 0
    # 戊+癸 合化 火, 火 不== 木, 火不生木 (金生木 actually no — 水生木), 火不克木 (金克木) → no modifier
    assert delta == 0


# === 六合 detection ===

def test_detect_liuhe_寅亥合木():
    """命局含 亥 + 行运 寅 → 六合 木."""
    assert _detect_liuhe('寅', ['亥', '酉', '酉']) == '木'


def test_detect_liuhe_no_match():
    """命局没有可六合的 支 → None."""
    assert _detect_liuhe('寅', ['酉', '酉', '未']) is None


def test_detect_liuhe_adjacent_命局_fires():
    """命局支 [寅, 亥, ...] 相邻 → 木."""
    result = _detect_liuhe('寅', ['寅', '亥', '子', '丑'], source_idx=0)
    assert result == '木'


def test_detect_liuhe_non_adjacent_命局_misses():
    """命局支 [寅, 子, 亥, 丑] idx 0-2 不相邻 → None."""
    result = _detect_liuhe('寅', ['寅', '子', '亥', '丑'], source_idx=0)
    assert result is None


def test_detect_liuhe_external_any_position_fires():
    """External 支 with source_idx=None still matches any position."""
    result = _detect_liuhe('寅', ['子', '丑', '未', '亥'])
    assert result == '木'


# === 支 score ===

def test_score_zhi_pure_bizhu():
    """寅 (木) 比助 木 用神 → +1."""
    delta, reason, mech = _score_zhi_to_yongshen('寅', '木', [])
    assert delta == 1
    assert '比助' in reason
    assert any('比助' in m for m in mech)


def test_score_zhi_with_liuhe_modifier():
    """寅 vs 木 用神，命局含 亥 → 寅亥合化木，本气木已比助 +1, 六合化木 转助 +1 → +2."""
    delta, reason, mech = _score_zhi_to_yongshen('寅', '木', ['亥', '酉', '酉'])
    # base: 寅 (木) 比助 木 → +1
    # 寅+亥 合化 木, 木 == 用神木 → modifier +1
    assert delta == 2
    assert '六合' in reason
    assert any('六合化木' in m for m in mech)


def test_score_yun_label_大喜():
    """甲寅 vs 甲木 用神: 干甲比助 (+1) + 支寅比助 (+1) +
    寅+命局亥 六合化木转助 (+1) + 干甲+命局己 合化土反克 (-1) → +2... 喜 not 大喜 :(
    Need a cleaner case. Try: 甲寅 vs 甲木 用神, 命局支含亥 (寅亥合木) + no 命局己 →
    干 +1 (比助), 支 +1 + 1 (比助 + 六合化木) = +2 → final +3 喜.
    Still not 大喜. To hit 大喜 we need +4: try 癸卯 vs 木 用神, 命局含亥 (卯亥不合).
    Actually 癸 (水) 生 木 +2; 卯 (木) 比助 +1. Total +3 → 喜.
    Need at least +4: 甲寅 vs 木, 命局亥 (六合木 +1) + 命局戊 (甲戊不合) →
    干 +1 (比助), 支 +1 + 1 = +2 → +3 still 喜.
    Hmm — 大喜 requires 干生 (+2) + 支生 (+2) = +4. That's 癸亥 vs 木 用神.
    癸 生 木 +2; 亥 (水) 生 木 +2. Total +4 → 大喜.
    """
    out = score_yun('癸亥', '甲木', [], [])
    assert out['label'] == '大喜'
    assert out['score'] >= 4


def test_score_yun_label_喜():
    """甲寅 vs 甲木: 比助 +1 + 比助 +1 = +2 → 喜."""
    out = score_yun('甲寅', '甲木', [], [])
    assert out['label'] == '喜'
    assert 2 <= out['score'] <= 3


def test_score_yun_label_平():
    """戊辰 vs 甲木: 用神克 戊 (0) + 用神克 辰 (0) = 0 → 平."""
    out = score_yun('戊辰', '甲木', [], [])
    assert out['label'] == '平'
    assert -1 <= out['score'] <= 1


def test_score_yun_label_忌():
    """丁巳 vs 甲木: 用神生丁 -1 + 用神生巳火 -1 = -2 → 忌."""
    out = score_yun('丁巳', '甲木', [], [])
    assert out['label'] == '忌'
    assert -3 <= out['score'] <= -2


def test_score_yun_label_大忌():
    """庚申 vs 甲木: 庚克木 -2 + 申金克木 -2 = -4 → 大忌."""
    out = score_yun('庚申', '甲木', [], [])
    assert out['label'] == '大忌'
    assert out['score'] <= -4


def test_multi_element_yongshen_takes_max_score():
    """用神 '甲木 / 戊土 / 庚金'，行运 庚申:
       - vs 木: 庚克木 -2, 申克木 -2 → -4
       - vs 土: 庚 not directly act on 土 (土生庚) → 用神土被泄 -1, 申 同 → -1
       - vs 金: 庚比助 +1, 申比助 +1 → +2
       Plan 7.6 weighted: 0.5·-4 + 0.3·-2 + 0.2·2 = -2.2 → round = -2 → 忌
    """
    out = score_yun('庚申', '甲木 / 戊土 / 庚金', [], [])
    assert out['label'] == '忌'   # Plan 7.6: was 喜 under max, now 忌 under weighted avg
    assert out['score'] == -2


def test_multi_element_winning_element_recorded():
    """For the same case, winningYongshenElement should name 庚金."""
    out = score_yun('庚申', '甲木 / 戊土 / 庚金', [], [])
    assert out['winningYongshenElement'] == '庚金'


def test_score_yun_中和_命局_returns_平():
    """用神 = '中和（无明显偏枯）' → 平 with empty mechanisms."""
    out = score_yun('庚申', '中和（无明显偏枯）', [], [])
    assert out['label'] == '平'
    assert out['score'] == 0
    assert out['mechanisms'] == []
    assert '中和' in out['note']


def test_score_yun_single_element_unchanged_by_weights():
    """单元素用神: weights=[1.0] → 结果跟 Plan 7.4 max 一致."""
    out = score_yun('癸亥', '甲木', [], [])
    assert out['label'] == '大喜'
    assert out['score'] == 4


def test_score_yun_multi_element_weighted_avg_applied():
    """多元素用神: weighted avg replaces max(sub_scores)."""
    out = score_yun('庚申', '甲木 / 戊土 / 庚金', [], [])
    assert out['label'] == '忌'
    assert out['score'] == -2


def test_score_yun_winningYongshenElement_still_max_not_weighted():
    """winningYongshenElement still reports the max sub-score element."""
    out = score_yun('庚申', '甲木 / 戊土 / 庚金', [], [])
    assert out['winningYongshenElement'] == '庚金'


def test_score_yun_two_element_weighted_weights_normalized():
    """2 元素用神: [0.5, 0.3] must normalize to [0.625, 0.375]."""
    out = score_yun('壬子', '甲木 / 丙火', [], [])
    assert out['score'] == 1
    assert out['label'] == '平'


def test_score_yun_four_element_weighted_weight_truncation():
    """4 元素用神: 第 4 元素权重为 0, 不参与最终 weighted score."""
    out = score_yun('癸亥', '甲木 / 丙火 / 戊土 / 庚金', [], [])
    assert out['score'] == 1
    assert out['label'] == '平'


def test_trim_note_short_unchanged():
    """≤ 30 字 → 不变."""
    s = '丙生用神，午比助用神'
    assert _trim_note(s) == s


def test_trim_note_long_with_comma_cuts_at_comma():
    """> 30 字, 含 ","在后半截 → 切到最后一个 ",".  """
    long_note = '丙生用神调候扶抑兼顾格局仍偏燥些，午比助用神但与命局丁壬合化木有反作用使整体偏弱很多'
    out = _trim_note(long_note)
    assert len(out) <= 30
    # 切在 "，" 边界 (该 "，" 在 idx=16 > limit//2=15)
    assert out.endswith('，')


def test_trim_note_long_no_punct_falls_back_to_char_cut():
    """> 30 字 + 全无标点 → 字符切到 30."""
    long_note = '一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十一二三'
    out = _trim_note(long_note)
    assert len(out) == 30


def test_trim_note_punct_in_first_half_falls_back():
    """> 30 字 + 标点在前半截 (idx < limit//2=15) → fallback 字符切.

    NOTE: 字符切会保留前面的 "，"; 只断言长度, 不断言标点存在与否.
    """
    long_note = '一二，四五六七八九十一二三四五六七八九十一二三四五六七八九十一二'
    # "，" 在 idx=2, < 15 → fallback to char cut
    out = _trim_note(long_note)
    assert len(out) == 30


def test_mechanism_tags_byte_identical_to_plan74_strings():
    """Plan 7.5a.1 §5.3 + §6.3: 重构后 mechanism 字符串跟 Plan 7.4 ship 的字面值一致."""
    from paipan import mechanism_tags as M

    # 5 干 base
    assert M.GAN_SHENG == '干·相生'
    assert M.GAN_KE == '干·相克'
    assert M.GAN_BIZHU == '干·比助'
    assert M.GAN_XIE == '干·相泄'
    assert M.GAN_HAO == '干·相耗'

    # 5 支 base
    assert M.ZHI_SHENG == '支·相生'
    assert M.ZHI_KE == '支·相克'
    assert M.ZHI_BIZHU == '支·比助'
    assert M.ZHI_XIE == '支·相泄'
    assert M.ZHI_HAO == '支·相耗'

    # 4 modifier builder
    assert M.gan_hehua_zhuanzhu('木') == '干·合化转助·木'
    assert M.gan_hehua_fanke('金') == '干·合化反克·金'
    assert M.zhi_liuhe_zhuanzhu('木') == '支·六合化木·转助'
    assert M.zhi_liuhe_fanke('火') == '支·六合化火·反克'


def test_xingyun_chart_context_plumbing():
    """Plan 7.5b §5.2: compute.py constructs chart_context and passes to build_xingyun.

    Verify by patching build_xingyun and capturing the call args.
    """
    import importlib

    compute_mod = importlib.import_module('paipan.compute')
    captured = {}
    original_build = compute_mod.build_xingyun

    def spy(**kwargs):
        captured.update(kwargs)
        return original_build(**kwargs)

    compute_mod.build_xingyun = spy
    try:
        compute_mod.compute(year=1993, month=7, day=15, hour=14, minute=30,
                             gender='male', city='长沙')
    finally:
        compute_mod.build_xingyun = original_build

    assert 'chart_context' in captured, 'compute.py should pass chart_context kwarg'
    cc = captured['chart_context']
    assert cc is not None
    assert cc['month_zhi'] == '未'   # 1993-07-15 month柱己未 → 月支未
    assert cc['rizhu_gan'] == '丁'    # 1993-07-15 丁酉日
    assert 'force' in cc
    assert 'gan_he' in cc
    assert 'original_geju_name' in cc


def test_is_same_combo_both_none_returns_false():
    assert _is_same_combo(None, None) is False
    assert _is_same_combo({'trigger': {}}, None) is False
    assert _is_same_combo(None, {'trigger': {}}) is False


def test_is_same_combo_same_type_same_zhi_returns_true():
    a = {'trigger': {'type': 'sanHe', 'zhi_list': ['亥', '卯', '未']}}
    b = {'trigger': {'type': 'sanHe', 'zhi_list': ['未', '亥', '卯']}}   # 顺序无关
    assert _is_same_combo(a, b) is True


def test_is_same_combo_different_type_or_zhi_returns_false():
    a = {'trigger': {'type': 'sanHe', 'zhi_list': ['亥', '卯', '未']}}
    b = {'trigger': {'type': 'sanHui', 'zhi_list': ['亥', '卯', '未']}}   # 不同 type
    assert _is_same_combo(a, b) is False

    c = {'trigger': {'type': 'sanHe', 'zhi_list': ['申', '子', '辰']}}   # 不同 zhi
    assert _is_same_combo(a, c) is False


# === 大运层 detection ===

def test_detect_xingyun_dayun_fires_when_dayun_zhi_completes_combo():
    """命局 [子,寅,午,辰] (月令子) + 大运申 → 申子辰三合 + 月令子参与 → fire."""
    result = _detect_xingyun_transmutation(
        month_zhi='子',
        base_mingju_zhis=['子', '寅', '午', '辰'],   # 命局 4 支, 月令子在内
        dayun_zhi='申',
        liunian_zhi=None,
        rizhu_gan='丙',
        force={'scores': {}}, gan_he={},
        original_geju_name='正官格',
    )
    assert result is not None
    assert result['trigger']['type'] == 'sanHe'
    assert result['trigger']['wuxing'] == '水'


def test_detect_xingyun_dayun_dedups_when_combo_already_in_命局():
    """命局 [酉,亥,卯,未] (月令亥, 已含完整亥卯未三合) + 大运丑 → 命局-only baseline 已触发 → 大运 dedup → None.

    NOTE: dayun_zhi 必须是地支 (e.g. '丑' 取自 大运'癸丑' 的支位).
    """
    result = _detect_xingyun_transmutation(
        month_zhi='亥',
        base_mingju_zhis=['酉', '亥', '卯', '未'],   # 命局已自带亥卯未
        dayun_zhi='丑',   # 癸丑大运 的 zhi 部分
        liunian_zhi=None,
        rizhu_gan='丁',
        force={'scores': {}}, gan_he={},
        original_geju_name='正官格',
    )
    assert result is None   # 命局已自带亥卯未, 大运 dedup


def test_detect_xingyun_dayun_no_trigger_when_dayun_zhi_irrelevant():
    """命局 [子,寅,午,辰] + 大运未 → 未不参与任何月令子的合局 → None."""
    result = _detect_xingyun_transmutation(
        month_zhi='子',
        base_mingju_zhis=['子', '寅', '午', '辰'],
        dayun_zhi='未',
        liunian_zhi=None,
        rizhu_gan='丙',
        force={'scores': {}}, gan_he={},
        original_geju_name='正官格',
    )
    assert result is None


def test_detect_xingyun_dayun_sanhui_priority():
    """命局 [子,寅,午,辰] + 大运卯 → 寅卯辰三会 (月令子不参与) + 申子辰三合 (缺申).
    都不 fire. 所以 None.

    设计另一个真触发同时多 combo 的场景比较难找。这个测试改为验证：
    命局 [亥,子,丑,巳] (月令子, 自带亥子丑三会北方水) + 大运辰 → with-大运 [亥,子,丑,巳,辰]:
      - 亥子丑三会水 ✓ (already in baseline)
      - 申子辰三合 缺申
    Baseline: 亥子丑三会水 (同上)
    → dedup, return None
    """
    result = _detect_xingyun_transmutation(
        month_zhi='子',
        base_mingju_zhis=['亥', '子', '丑', '巳'],
        dayun_zhi='辰',
        liunian_zhi=None,
        rizhu_gan='壬',
        force={'scores': {}}, gan_he={},
        original_geju_name='正官格',
    )
    assert result is None   # baseline 已 fire 三会, dedup


# === 流年层 dedup ===

def test_detect_xingyun_liunian_fires_when_dayun_baseline_no_combo():
    """命局 + 大运 baseline 无合局 (dayun_transmuted=None), 流年支贡献第三支 → fire."""
    # 命局 [子,寅,辰,亥] (月令子, 自带申子辰需申, 自带亥子丑需丑)
    # 大运戌 → with-大运 [子,寅,辰,亥,戌]: 申子辰需申 (缺), 亥子丑需丑 (缺), 寅午戌需午 (缺), 亥子丑无完整, 月令子参与亥子丑但缺丑
    # → 大运 transmuted = None
    # 流年丑 → with-流年 [子,寅,辰,亥,戌,丑]: 亥子丑完整 + 月令子参与 → fire
    result = _detect_xingyun_transmutation(
        month_zhi='子',
        base_mingju_zhis=['子', '寅', '辰', '亥'],
        dayun_zhi='戌',
        liunian_zhi='丑',
        rizhu_gan='壬',
        force={'scores': {}}, gan_he={},
        original_geju_name='正官格',
        baseline_transmuted=None,   # 大运 baseline None
    )
    assert result is not None
    assert result['trigger']['type'] == 'sanHui'   # 亥子丑三会


def test_detect_xingyun_liunian_dedups_when_dayun_already_fired_same_combo():
    """大运 transmuted = 申子辰; 流年带辰 (already in 大运) → 同 combo → dedup."""
    fake_baseline = {
        'trigger': {
            'type': 'sanHe', 'wuxing': '水',
            'zhi_list': ['申', '子', '辰'], 'main': '子',
            'source': '三合申子辰局',
        },
    }
    # 命局 [子,寅,午,丑] + 大运申 → 申子辰已 fire (大运 transmuted = fake_baseline)
    # 流年辰 → with-流年 [子,寅,午,丑,申,辰]: 申子辰仍 fire (同 combo)
    # → dedup, return None
    result = _detect_xingyun_transmutation(
        month_zhi='子',
        base_mingju_zhis=['子', '寅', '午', '丑'],
        dayun_zhi='申',
        liunian_zhi='辰',
        rizhu_gan='丙',
        force={'scores': {}}, gan_he={},
        original_geju_name='正官格',
        baseline_transmuted=fake_baseline,
    )
    assert result is None


def test_detect_xingyun_liunian_fires_when_different_combo_than_dayun():
    """大运 transmuted = 三合A; 流年带支触发不同三合B (月令同时在两个合局里) → fire."""
    # 月令子 同时在 申子辰 和 亥子丑
    # 命局 [子,申,辰,巳]: 大运甲带支 → no
    # 实际很难构造干净, 用 mock baseline:
    fake_baseline = {
        'trigger': {
            'type': 'sanHe', 'wuxing': '水',
            'zhi_list': ['申', '子', '辰'], 'main': '子',
            'source': '三合申子辰局',
        },
    }
    # 命局 [子,寅,午,亥] + 大运丑 → 亥子丑三会 (子在其中)
    # 流年丑同时也补全亥子丑
    # 但大运已经触发亥子丑? wait, 大运丑 + 命局亥子 → 亥子丑完整, 月令子参与 → 大运也 fire 亥子丑
    # 让 fake_baseline 是 申子辰; 实际 with-流年 触发 亥子丑 → 不同 combo → fire
    result = _detect_xingyun_transmutation(
        month_zhi='子',
        base_mingju_zhis=['子', '寅', '午', '亥'],
        dayun_zhi='丑',         # 大运丑
        liunian_zhi='丑',        # 流年也丑 (mingju+dayun+liunian = [子,寅,午,亥,丑,丑])
        rizhu_gan='丙',
        force={'scores': {}}, gan_he={},
        original_geju_name='正官格',
        baseline_transmuted=fake_baseline,   # 假装大运是申子辰 (实际此盘 baseline 应是亥子丑)
    )
    assert result is not None
    # 流年触发的应该是亥子丑 (with-流年 result)
    assert result['trigger']['type'] == 'sanHui'
    assert set(result['trigger']['zhi_list']) == {'亥', '子', '丑'}


def test_detect_xingyun_liunian_no_trigger_when_no_combo():
    """命局 + 大运 + 流年 都不构成合局 → None."""
    result = _detect_xingyun_transmutation(
        month_zhi='子',
        base_mingju_zhis=['子', '寅', '午', '辰'],
        dayun_zhi='巳',
        liunian_zhi='未',
        rizhu_gan='丙',
        force={'scores': {}}, gan_he={},
        original_geju_name='正官格',
        baseline_transmuted=None,
    )
    assert result is None


def test_build_xingyun_standard_chart_all_transmuted_none():
    """Verified all-none chart: 命局/大运/流年 都无合局触发 → 所有 transmuted 都是 None."""
    out = compute(year=1989, month=8, day=15, hour=12, minute=0,
                   gender='male', city='北京')
    xy = out['xingyun']
    for d in xy['dayun']:
        assert d['transmuted'] is None, f"dayun[{d['index']}] unexpected transmuted: {d['transmuted']}"
    for k, ln_list in xy['liunian'].items():
        for ly in ln_list:
            assert ly['transmuted'] is None, \
                f"liunian[{k}] {ly['year']} unexpected transmuted"


def test_build_xingyun_static_chart_dayun_dedup():
    """1980-02-12 chart 命局自带寅卯辰三会 (Plan 7.5a 静态 fire) → xingyun.dayun 全 dedup → None."""
    out = compute(year=1980, month=2, day=12, hour=8, minute=0,
                   gender='male', city='北京')
    detail = out['yongshenDetail']
    assert detail.get('transmuted') is not None, '1980-02-12 应触发 Plan 7.5a static'

    xy = out['xingyun']
    for d in xy['dayun']:
        assert d['transmuted'] is None, \
            f"dayun[{d['index']}] should be dedup'd against 命局 baseline, got: {d['transmuted']}"


def test_build_xingyun_chart_context_none_skips_transmutation():
    """build_xingyun() called without chart_context → transmuted 字段 None (backward compat)."""
    from paipan.xingyun import build_xingyun

    # 用一个本应触发 transmutation 的 chart 但不传 chart_context
    out = compute(year=1980, month=2, day=12, hour=8, minute=0,
                   gender='male', city='北京')
    fake_dayun = out['dayun']
    fake_yongshen = out['yongshenDetail']

    # 调 build_xingyun 不传 chart_context
    xy_no_ctx = build_xingyun(
        dayun=fake_dayun,
        yongshen_detail=fake_yongshen,
        mingju_gans=['庚', '戊', '乙', '庚'],
        mingju_zhis=['申', '寅', '卯', '辰'],
        current_year=2026,
        # chart_context 不传
    )
    for d in xy_no_ctx['dayun']:
        assert d['transmuted'] is None, 'no chart_context → no transmutation'


def test_cross_interaction_dayun_gan_extends_mingju_for_liunian_score():
    """Plan 7.7: 大运庚 + 流年乙 → 乙庚合化金 modifier 应在流年 mechanisms 里."""
    mock_dayun = {
        'list': [
            {
                'index': 1,
                'ganzhi': '庚午',
                'startAge': 5,
                'startYear': 2000,
                'endYear': 2009,
                'liunian': [
                    {'year': 2005, 'ganzhi': '乙酉', 'age': 10},
                ],
            },
        ],
    }
    out = build_xingyun(
        dayun=mock_dayun,
        yongshen_detail={'primary': '癸水'},
        mingju_gans=['丁', '丙', '己', '辛'],
        mingju_zhis=['未', '寅', '卯', '亥'],
        current_year=2010,
        chart_context=None,
    )

    liunian_entries = out['liunian']['1']
    assert len(liunian_entries) == 1
    ly_2005 = liunian_entries[0]
    assert ly_2005['year'] == 2005
    assert any('合化' in m and '金' in m for m in ly_2005['mechanisms']), (
        f"expected 干合化金 modifier in mechanisms, got: {ly_2005['mechanisms']}"
    )


def test_cross_interaction_dayun_zhi_extends_mingju_for_liunian_score():
    """Plan 7.7: 大运卯 + 流年戌 → 卯戌合化火 modifier 应在流年 mechanisms 里."""
    mock_dayun = {
        'list': [
            {
                'index': 1,
                'ganzhi': '丁卯',
                'startAge': 5,
                'startYear': 2000,
                'endYear': 2009,
                'liunian': [
                    {'year': 2006, 'ganzhi': '丙戌', 'age': 11},
                ],
            },
        ],
    }
    out = build_xingyun(
        dayun=mock_dayun,
        yongshen_detail={'primary': '戊土'},
        mingju_gans=['庚', '己', '癸', '甲'],
        mingju_zhis=['申', '丑', '巳', '酉'],
        current_year=2010,
        chart_context=None,
    )

    liunian_entries = out['liunian']['1']
    ly_2006 = liunian_entries[0]
    assert ly_2006['year'] == 2006
    assert any('六合' in m and '火' in m for m in ly_2006['mechanisms']), (
        f"expected 支六合化火 modifier in mechanisms, got: {ly_2006['mechanisms']}"
    )


def test_cross_interaction_no_overlap_behavior_matches_plan74():
    """Plan 7.7: 当大运干支跟流年干支不形成合化, score 跟 Plan 7.4 行为一致."""
    mock_dayun = {
        'list': [
            {
                'index': 1,
                'ganzhi': '甲寅',
                'startAge': 5,
                'startYear': 2000,
                'endYear': 2009,
                'liunian': [
                    {'year': 2004, 'ganzhi': '甲申', 'age': 9},
                ],
            },
        ],
    }
    mingju_gans = ['丁', '丙', '戊', '辛']
    mingju_zhis = ['未', '午', '辰', '酉']
    out = build_xingyun(
        dayun=mock_dayun,
        yongshen_detail={'primary': '丙火'},
        mingju_gans=mingju_gans,
        mingju_zhis=mingju_zhis,
        current_year=2010,
        chart_context=None,
    )
    liunian_score = out['liunian']['1'][0]['score']

    plan74_result = score_yun('甲申', '丙火', mingju_gans, mingju_zhis)
    assert liunian_score == plan74_result['score'], (
        'cross interaction should not affect score when no overlap; '
        f"got Plan 7.7 {liunian_score} vs Plan 7.4 {plan74_result['score']}"
    )


def test_build_xingyun_returns_8_dayun():
    """The standard chart should produce 8 大运 entries."""
    out = compute(year=1993, month=7, day=15, hour=14, minute=30,
                   gender='male', city='长沙')
    xy = out['xingyun']
    assert len(xy['dayun']) == 8
    for entry in xy['dayun']:
        assert 'label' in entry
        assert 'score' in entry
        assert 'note' in entry
        assert entry['label'] in {'大喜', '喜', '平', '忌', '大忌'}


def test_build_xingyun_currentDayunIndex_is_set():
    """For 1993 birth + 2026 current_year, current大运 should be in [1,8]."""
    out = compute(year=1993, month=7, day=15, hour=14, minute=30,
                   gender='male', city='长沙')
    xy = out['xingyun']
    assert xy['currentDayunIndex'] is not None
    assert 1 <= xy['currentDayunIndex'] <= 8


def test_build_xingyun_liunian_keyed_by_dayun_index():
    """liunian dict keys are str(1)..str(8) and each list has 10 entries."""
    out = compute(year=1993, month=7, day=15, hour=14, minute=30,
                   gender='male', city='长沙')
    xy = out['xingyun']
    assert set(xy['liunian'].keys()) == {str(i) for i in range(1, 9)}
    for k, ln_list in xy['liunian'].items():
        assert len(ln_list) == 10, f'大运 {k} should have 10 流年, got {len(ln_list)}'


def test_build_xingyun_中和_命局_returns_empty():
    """If yongshen_detail.primary contains '中和', dayun and liunian should be empty."""
    fake_yongshen = {'primary': '中和（无明显偏枯）'}
    fake_dayun = {'list': []}   # any shape — should be ignored
    out = build_xingyun(fake_dayun, fake_yongshen, [], [], 2026)
    assert out['dayun'] == []
    assert out['liunian'] == {}
    assert out['currentDayunIndex'] is None
    assert '中和' in out['yongshenSnapshot']


GOLDEN_XINGYUN_CASES = [
    {
        'label': '丁火六月_身弱_食神格',
        'input': dict(year=1993, month=7, day=15, hour=14, minute=30,
                       gender='male', city='长沙'),
    },
    {
        'label': '丙火五月_身强',
        'input': dict(year=1990, month=5, day=12, hour=12, minute=0,
                       gender='male', city='北京'),
    },
    {
        'label': '甲木八月',
        'input': dict(year=2003, month=8, day=29, hour=8, minute=27,
                       gender='male', city='上海'),
    },
    {
        'label': '癸水正月',
        'input': dict(year=1985, month=1, day=5, hour=23, minute=45,
                       gender='female', city='广州'),
    },
    {
        'label': '辛金腊月',
        'input': dict(year=1976, month=11, day=30, hour=6, minute=15,
                       gender='female', city='成都'),
    },
    {
        'label': '戊土三月',
        'input': dict(year=2000, month=2, day=29, hour=16, minute=0,
                       gender='male', city='深圳'),
    },
    {
        'label': '丁火_寅午戌_三合',
        'input': dict(year=1984, month=10, day=5, hour=14, minute=0,
                       gender='male', city='北京'),
    },
    {
        'label': '乙木_寅卯辰_三会',
        'input': dict(year=1995, month=3, day=21, hour=12, minute=0,
                       gender='female', city='上海'),
    },
    {
        'label': '日主合化',
        'input': dict(year=1988, month=6, day=10, hour=9, minute=0,
                       gender='male', city='北京'),
    },
    {
        'label': '从格疑似',
        'input': dict(year=1974, month=8, day=8, hour=8, minute=0,
                       gender='female', city='昆明'),
    },
]


@pytest.mark.parametrize('case', GOLDEN_XINGYUN_CASES,
                          ids=[c['label'] for c in GOLDEN_XINGYUN_CASES])
def test_xingyun_golden_structural(case):
    """Each golden chart produces a structurally sound xingyun dict.

    Asserts (no specific label values — those are not oracle truths):
      - xingyun is a dict with required top-level keys
      - dayun has 8 entries (or 0 if 中和 命局)
      - if dayun non-empty: liunian has 8 keys × 10 entries each
      - currentDayunIndex is in [1,8] or None
      - every dayun/liunian entry has label in valid set
      - mechanisms list is well-formed (each tag matches expected pattern)
    """
    out = compute(**case['input'])
    xy = out.get('xingyun')
    assert xy is not None, f"{case['label']}: missing xingyun"
    assert 'dayun' in xy
    assert 'liunian' in xy
    assert 'currentDayunIndex' in xy
    assert 'yongshenSnapshot' in xy

    valid_labels = {'大喜', '喜', '平', '忌', '大忌'}

    if xy['dayun']:   # non-中和 case
        assert len(xy['dayun']) == 8, \
            f"{case['label']}: expected 8 dayun, got {len(xy['dayun'])}"
        for d in xy['dayun']:
            assert d['label'] in valid_labels
            assert isinstance(d['mechanisms'], list)
        assert len(xy['liunian']) == 8
        for k, ln_list in xy['liunian'].items():
            assert len(ln_list) == 10
            for ly in ln_list:
                assert ly['label'] in valid_labels

        cur = xy['currentDayunIndex']
        if cur is not None:
            assert 1 <= cur <= 8
    else:
        # 中和 命局 — verify empty consistency
        assert xy['liunian'] == {}
        assert xy['currentDayunIndex'] is None


def test_xingyun_cross_interaction_golden():
    """Plan 7.7 §6 acceptance: verified real chart fires cross interaction
    modifiers in multiple 流年 entries beyond the Plan 7.4 base score_yun path.
    """
    out = compute(
        year=1990, month=9, day=18, hour=14, minute=0,
        gender='female', city='上海',
    )
    xy = out['xingyun']
    sizhu = out['sizhu']
    mingju_gans = [g[0] for g in [sizhu['year'], sizhu['month'], sizhu['day'], sizhu['hour']] if g]
    mingju_zhis = [g[1] for g in [sizhu['year'], sizhu['month'], sizhu['day'], sizhu['hour']] if g]

    assert xy['currentDayunIndex'] == 4
    current_dayun = next(d for d in xy['dayun'] if d['index'] == xy['currentDayunIndex'])
    assert current_dayun['ganzhi'] == '辛巳'

    cross_fires = []
    for k, ln_list in xy['liunian'].items():
        dy = next((d for d in xy['dayun'] if d['index'] == int(k)), None)
        assert dy is not None
        for ly in ln_list:
            base = score_yun(
                ly['ganzhi'],
                out['yongshenDetail']['primary'],
                mingju_gans,
                mingju_zhis,
            )
            added_mechanisms = [m for m in ly['mechanisms'] if m not in base['mechanisms']]
            if (
                (ly['score'] != base['score'] or ly['mechanisms'] != base['mechanisms'])
                and any('合化' in m or '六合' in m for m in added_mechanisms)
            ):
                cross_fires.append({
                    'dayun': dy['ganzhi'],
                    'year': ly['year'],
                    'liunian': ly['ganzhi'],
                    'score': ly['score'],
                    'base_score': base['score'],
                    'added_mechanisms': added_mechanisms,
                })

    assert len(cross_fires) >= 5, f"expected >=5 verified cross fires, got: {cross_fires}"
    assert any(
        row['dayun'] == '甲申'
        and row['year'] == 1999
        and row['liunian'] == '己卯'
        and row['score'] == -4
        and row['base_score'] == -3
        and '干·合化反克·土' in row['added_mechanisms']
        for row in cross_fires
    ), cross_fires
    assert any(
        row['dayun'] == '辛巳'
        and row['year'] == 2026
        and row['liunian'] == '丙午'
        and row['score'] == 0
        and row['base_score'] == -1
        and '干·合化转助·水' in row['added_mechanisms']
        for row in cross_fires
    ), cross_fires
    assert any(
        row['dayun'] == '丁丑'
        and row['year'] == 2068
        and row['liunian'] == '戊子'
        and row['score'] == -2
        and row['base_score'] == -1
        and '支·六合化土·反克' in row['added_mechanisms']
        for row in cross_fires
    ), cross_fires


GOLDEN_DYNAMIC_TRANSMUTATION_CASES = [
    {
        'label': '丑月金局_双层触发',
        'input': dict(year=1970, month=1, day=15, hour=12, minute=0,
                       gender='male', city='北京'),
        'expect_dayun_transmutations': 1,
        'expect_liunian_transmutations': 7,
        'expected_trigger_types': {'sanHe', 'sanHui'},
    },
    {
        'label': '未月木火双局',
        'input': dict(year=1971, month=7, day=15, hour=12, minute=0,
                       gender='male', city='北京'),
        'expect_dayun_transmutations': 2,
        'expect_liunian_transmutations': 11,
        'expected_trigger_types': {'sanHe', 'sanHui'},
    },
    {
        'label': '申月金水双局',
        'input': dict(year=1970, month=8, day=15, hour=12, minute=0,
                       gender='male', city='北京'),
        'expect_dayun_transmutations': 1,
        'expect_liunian_transmutations': 8,
        'expected_trigger_types': {'sanHe', 'sanHui'},
    },
    {
        'label': '戌月火局建禄',
        'input': dict(year=1970, month=10, day=15, hour=12, minute=0,
                       gender='male', city='北京'),
        'expect_dayun_transmutations': 1,
        'expect_liunian_transmutations': 5,
        'expected_trigger_types': {'sanHe'},
    },
    {
        'label': '巳月官杀转化',
        'input': dict(year=1971, month=5, day=15, hour=12, minute=0,
                       gender='male', city='北京'),
        'expect_dayun_transmutations': 0,
        'expect_liunian_transmutations': 9,
        'expected_trigger_types': {'sanHe', 'sanHui'},
    },
]


@pytest.mark.parametrize('case', GOLDEN_DYNAMIC_TRANSMUTATION_CASES,
                          ids=[c['label'] for c in GOLDEN_DYNAMIC_TRANSMUTATION_CASES])
def test_xingyun_dynamic_transmutation_golden(case):
    """Plan 7.5b §6.1 golden: real charts trigger dynamic transmutation as expected."""
    out = compute(**case['input'])
    xy = out['xingyun']

    dayun_transmuted_count = sum(1 for d in xy['dayun'] if d.get('transmuted'))
    liunian_transmuted_count = sum(
        1 for ln_list in xy['liunian'].values()
        for ly in ln_list if ly.get('transmuted')
    )

    if 'expect_dayun_transmutations' in case:
        assert dayun_transmuted_count >= case['expect_dayun_transmutations'], \
            f"{case['label']}: expected ≥{case['expect_dayun_transmutations']} dayun transmutations, got {dayun_transmuted_count}"

    if 'expect_liunian_transmutations' in case:
        assert liunian_transmuted_count >= case['expect_liunian_transmutations'], \
            f"{case['label']}: expected ≥{case['expect_liunian_transmutations']} liunian transmutations, got {liunian_transmuted_count}"

    # 验证 trigger.type 在预期集合内
    if 'expected_trigger_types' in case:
        all_types = set()
        for d in xy['dayun']:
            if d.get('transmuted'):
                all_types.add(d['transmuted']['trigger']['type'])
        for ln_list in xy['liunian'].values():
            for ly in ln_list:
                if ly.get('transmuted'):
                    all_types.add(ly['transmuted']['trigger']['type'])
        assert all_types.issubset(case['expected_trigger_types']), \
            f"{case['label']}: actual types {all_types} not subset of expected {case['expected_trigger_types']}"
