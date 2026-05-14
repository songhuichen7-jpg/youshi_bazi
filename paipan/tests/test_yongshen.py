"""Plan 7.3 yongshen engine — skeleton & integration."""
from __future__ import annotations

import pytest

from paipan import compute
from paipan.yongshen import (
    _compute_virtual_geju_name,
    _detect_transmutation,
    build_yongshen,
    compose_yongshen,
)


def test_chart_yongshen_is_string_for_compat():
    """Plan 7.3 §6.4: chart.paipan.yongshen MUST stay a string."""
    out = compute(year=1993, month=7, day=15, hour=14, minute=30,
                   gender='male', city='长沙')
    assert isinstance(out['yongshen'], str)
    assert out['yongshen']  # not empty


def test_chart_yongshen_detail_is_dict_with_required_keys():
    """Plan 7.3 §3.1: yongshenDetail dict has primary/candidates/warnings."""
    out = compute(year=1993, month=7, day=15, hour=14, minute=30,
                   gender='male', city='长沙')
    detail = out.get('yongshenDetail')
    assert isinstance(detail, dict)
    assert 'primary' in detail
    assert 'primaryReason' in detail
    assert 'candidates' in detail
    assert 'warnings' in detail
    assert isinstance(detail['candidates'], list)
    assert len(detail['candidates']) == 3
    methods = {c['method'] for c in detail['candidates']}
    assert methods == {'调候', '格局', '扶抑'}


def test_chart_yongshen_string_matches_detail_primary():
    """The string at top-level must equal yongshenDetail['primary']."""
    out = compute(year=1993, month=7, day=15, hour=14, minute=30,
                   gender='male', city='长沙')
    assert out['yongshen'] == out['yongshenDetail']['primary']


def test_chart_yongshen_transmuted_absent_when_no_combo():
    """Plan 7.5a §1: charts without 命局自带合局 should NOT have transmuted field.

    Standard 1993 chart (癸酉/己未/丁酉/丁未) has no 三合/三会 with 月令未:
      - 月令 未 → SAN_HE_JU 中 亥卯未 (需 命局含 亥+卯, 命局支只有酉/未/酉/未, 无)
      - 月令 未 → SAN_HUI 中 巳午未 (需 命局含 巳+午, 命局支无)
    所以应当无 transmutation.
    """
    out = compute(year=1993, month=7, day=15, hour=14, minute=30,
                   gender='male', city='长沙')
    detail = out['yongshenDetail']
    assert 'transmuted' not in detail or detail['transmuted'] is None


def test_tiaohou_yongshen_甲木_正月():
    """甲木生寅月 (正月) → expect tiaohou hit from 论甲木."""
    from paipan.yongshen import tiaohou_yongshen
    res = tiaohou_yongshen('甲', '寅')
    assert res is not None
    assert res['method'] == '调候'
    assert res['name'] is not None
    assert '穷通宝鉴' in res['source']


def test_tiaohou_yongshen_unknown_combination_returns_none():
    """Empty key returns None (e.g. None gan)."""
    from paipan.yongshen import tiaohou_yongshen
    # Use a key guaranteed missing in dict (won't match any real combination)
    res = tiaohou_yongshen('XX', '寅')   # XX is not a real gan
    assert res is None


def test_geju_yongshen_七杀格_with_食神_returns_食制():
    from paipan.yongshen import geju_yongshen
    force = {'scores': {'食神': 5, '七杀': 4}}
    res = geju_yongshen('七杀格', force, {})
    assert res is not None
    assert res['method'] == '格局'
    assert '食神' in res['name'] or '制' in res['name']
    assert '子平真诠' in res['source']


def test_geju_yongshen_unknown_geju_returns_none():
    from paipan.yongshen import geju_yongshen
    res = geju_yongshen('不存在的格局', {'scores': {}}, {})
    assert res is None


def test_geju_yongshen_格局不清_returns_none():
    from paipan.yongshen import geju_yongshen
    res = geju_yongshen('格局不清', {'scores': {}}, {})
    assert res is None


def test_fuyi_yongshen_身弱_returns_扶身_candidate():
    from paipan.yongshen import fuyi_yongshen
    res = fuyi_yongshen({'scores': {}}, '身弱')
    assert res is not None
    assert res['method'] == '扶抑'
    assert '滴天髓' in res['source']


def test_fuyi_yongshen_中和_returns_none():
    """中和 should produce no 扶抑 candidate."""
    from paipan.yongshen import fuyi_yongshen
    assert fuyi_yongshen({'scores': {}}, '中和') is None


def test_fuyi_yongshen_身强_returns_泄身_candidate():
    from paipan.yongshen import fuyi_yongshen
    res = fuyi_yongshen({'scores': {}}, '身强')
    assert res is not None
    assert res['method'] == '扶抑'


def test_fuyi_yongshen_极弱_returns_compound_扶身():
    """Plan 7.6: 极弱 dayStrength → FUYI_CASES '印 + 比劫（同扶）' rule fires."""
    from paipan.yongshen import fuyi_yongshen

    res = fuyi_yongshen({'scores': {}}, '极弱')
    assert res is not None
    assert res['method'] == '扶抑'
    assert '印' in res['name'] and '比劫' in res['name']
    assert '+' in res['name']
    assert res['source'].startswith('滴天髓')


def test_fuyi_yongshen_极强_returns_compound_双泄():
    """Plan 7.6: 极强 dayStrength → FUYI_CASES '官杀 + 食伤（双泄）' rule fires."""
    from paipan.yongshen import fuyi_yongshen

    res = fuyi_yongshen({'scores': {}}, '极强')
    assert res is not None
    assert res['method'] == '扶抑'
    assert '官杀' in res['name'] and '食伤' in res['name']
    assert '+' in res['name']
    assert res['source'].startswith('滴天髓')


def test_fuyi_yongshen_unknown_strength_returns_none():
    from paipan.yongshen import fuyi_yongshen
    assert fuyi_yongshen({'scores': {}}, None) is None
    assert fuyi_yongshen({'scores': {}}, 'something_weird') is None


def _candidate(method, name, note='', source=''):
    return {'method': method, 'name': name, 'note': note, 'source': source}


def test_compose_調候格局共指():
    t = _candidate('调候', '庚金', source='穷通宝鉴·论丁火·六月')
    g = _candidate('格局', '庚金', source='子平真诠·论七杀')
    out = compose_yongshen(t, g, None)
    assert out['primary'] == '庚金'
    assert out['primaryReason'] == '调候 + 格局共指'
    assert out['warnings'] == []


def test_compose_調候格局不同_warns():
    t = _candidate('调候', '庚金', source='穷通宝鉴·论丁火·六月')
    g = _candidate('格局', '印（化杀）', source='子平真诠·论七杀')
    out = compose_yongshen(t, g, None)
    assert out['primary'] == '庚金'
    assert out['primaryReason'] == '以调候为主'
    assert len(out['warnings']) == 1
    assert '古籍两派' in out['warnings'][0]


def test_compose_only_geju_when_no_tiaohou():
    g = _candidate('格局', '财（生官）', source='子平真诠·论正官')
    out = compose_yongshen(None, g, None)
    assert out['primary'] == '财（生官）'
    assert out['primaryReason'] == '格局法'


def test_compose_only_fuyi_as_last_resort():
    f = _candidate('扶抑', '印 / 比劫', source='滴天髓·衰旺')
    out = compose_yongshen(None, None, f)
    assert out['primary'] == '印 / 比劫'
    assert out['primaryReason'] == '扶抑法（前两法无明确结论）'


def test_compose_no_method_returns_中和():
    out = compose_yongshen(None, None, None)
    assert out['primary'] == '中和（无明显偏枯）'
    assert out['primaryReason'] == '三法皆无强候选'


def test_compose_candidates_always_3_in_fixed_order():
    """Even when methods produce no result, candidates list has 3 entries
    in order [调候, 格局, 扶抑] for stable LLM prompt rendering."""
    out = compose_yongshen(None, None, None)
    assert len(out['candidates']) == 3
    assert [c['method'] for c in out['candidates']] == ['调候', '格局', '扶抑']


# 5 五行 × 2 polarity = 10 entries.
# Day master 锚定 丁火 (阴), 配 12 月支主气支覆盖全部 10 个 (十神类, polarity) 组合.
@pytest.mark.parametrize('new_wuxing,rizhu_gan,main_zhi,expected', [
    # 印 (生我者): 木生火
    ('木', '丁', '卯', '偏印格'),    # 丁(阴) + 卯(阴乙) → 印 + same → 偏印
    ('木', '丁', '寅', '正印格'),    # 丁(阴) + 寅(阳甲) → 印 + opposite → 正印
    # 比劫 (同我者): 火
    ('火', '丁', '午', '比肩格'),    # 丁(阴) + 午(阴丁) → 比劫 + same → 比肩
    ('火', '丁', '巳', '劫财格'),    # 丁(阴) + 巳(阳丙) → 比劫 + opposite → 劫财
    # 食伤 (我生者): 火生土
    ('土', '丁', '未', '食神格'),    # 丁(阴) + 未(阴己) → 食伤 + same → 食神
    ('土', '丁', '辰', '伤官格'),    # 丁(阴) + 辰(阳戊) → 食伤 + opposite → 伤官
    # 财 (我克者): 火克金
    ('金', '丁', '酉', '偏财格'),    # 丁(阴) + 酉(阴辛) → 财 + same → 偏财
    ('金', '丁', '申', '正财格'),    # 丁(阴) + 申(阳庚) → 财 + opposite → 正财
    # 官杀 (克我者): 水克火
    ('水', '丁', '亥', '正官格'),    # 丁(阴) + 亥(阳壬) → 官杀 + opposite → 正官
    ('水', '丁', '子', '七杀格'),    # 丁(阴) + 子(阴癸) → 官杀 + same → 七杀
])
def test_compute_virtual_geju_name_covers_10_entries(
    new_wuxing, rizhu_gan, main_zhi, expected
):
    assert _compute_virtual_geju_name(new_wuxing, rizhu_gan, main_zhi) == expected


def test_detect_transmutation_sanhe_when_month_in_combo():
    """月令亥 + 命局含卯+未 → 亥卯未三合木局触发。"""
    result = _detect_transmutation(
        month_zhi='亥',
        mingju_zhis=['酉', '亥', '卯', '未'],
        rizhu_gan='丁',
        force={'scores': {}},
        gan_he={},
    )
    assert result is not None
    assert result['trigger']['type'] == 'sanHe'
    assert result['trigger']['wuxing'] == '木'
    assert result['to'] == '偏印格'   # 丁(阴)+卯(阴) → 印 + same


def test_detect_transmutation_sanhui_when_month_in_combo():
    """月令寅 + 命局含卯+辰 → 寅卯辰三会木方触发。"""
    result = _detect_transmutation(
        month_zhi='寅',
        mingju_zhis=['酉', '寅', '卯', '辰'],
        rizhu_gan='丙',
        force={'scores': {}},
        gan_he={},
    )
    assert result is not None
    assert result['trigger']['type'] == 'sanHui'
    assert result['trigger']['wuxing'] == '木'


def test_detect_transmutation_no_trigger_when_month_not_in_combo():
    """命局含 卯+未 但月令是 子 → 命局自带亥卯未三合 (没亥), 实际未触发。
    更严的负向测试：月令 子, 命局 卯/未/酉, 没合局.
    """
    result = _detect_transmutation(
        month_zhi='子',
        mingju_zhis=['酉', '子', '卯', '未'],
        rizhu_gan='丁',
        force={'scores': {}},
        gan_he={},
    )
    assert result is None   # 月令子不在亥卯未, 不在申子辰 (缺申/辰), 不在亥子丑 (缺亥/丑)


def test_detect_transmutation_no_trigger_when_partial_combo():
    """月令亥 + 命局只含卯 (缺未) → 不算完整三合，不触发。"""
    result = _detect_transmutation(
        month_zhi='亥',
        mingju_zhis=['酉', '亥', '卯', '酉'],
        rizhu_gan='丁',
        force={'scores': {}},
        gan_he={},
    )
    assert result is None


def test_detect_transmutation_sanhe_priority_over_sanhui():
    """构造同时触发 三合 + 三会 的极端 case (理论物理不可能 4 支同时凑两个)，
    单独单元测试 _detect_transmutation 内部排序逻辑：
    用一个 mock-like input 模拟两个 combo 都通过 (mingju_zhis 含 5 支).
    """
    # 月令子 + 命局含申+辰 → 申子辰 三合
    # 月令子 + 命局含亥+丑 → 亥子丑 三会  (5 支总)
    result = _detect_transmutation(
        month_zhi='子',
        mingju_zhis=['申', '子', '辰', '亥', '丑'],   # 5 支：测试用
        rizhu_gan='丙',
        force={'scores': {}},
        gan_he={},
    )
    assert result is not None
    assert result['trigger']['type'] == 'sanHe'   # 三合优先
    assert len(result['alternateTriggers']) == 1
    assert result['alternateTriggers'][0]['type'] == 'sanHui'


def test_build_yongshen_no_mingju_zhis_skips_transmutation():
    """build_yongshen() 不传 mingju_zhis (Plan 7.3 老调用方式) → 不挂 transmuted 字段。"""
    out = build_yongshen(
        rizhu_gan='丁',
        month_zhi='亥',
        force={'scores': {}, 'dayStrength': '中和'},
        geju='正官格',
        gan_he={},
        day_strength='中和',
        # mingju_zhis 不传
    )
    assert 'transmuted' not in out


def test_build_yongshen_with_mingju_zhis_no_combo_skips_transmutation():
    """传 mingju_zhis 但命局支不构成合局 → 也不挂 transmuted。"""
    out = build_yongshen(
        rizhu_gan='丁',
        month_zhi='未',
        force={'scores': {}, 'dayStrength': '中和'},
        geju='食神格',
        gan_he={},
        day_strength='中和',
        mingju_zhis=['酉', '未', '酉', '未'],   # 标准 1993 chart
    )
    assert 'transmuted' not in out


def test_build_yongshen_with_mingju_zhis_combo_attaches_transmuted():
    """命局自带亥卯未 → 挂 transmuted 字段, primaryReason 加 hint。"""
    out = build_yongshen(
        rizhu_gan='丁',
        month_zhi='亥',
        force={'scores': {}, 'dayStrength': '中和'},
        geju='正官格',
        gan_he={},
        day_strength='中和',
        mingju_zhis=['酉', '亥', '卯', '未'],
    )
    assert 'transmuted' in out
    t = out['transmuted']
    assert t['trigger']['type'] == 'sanHe'
    assert t['trigger']['wuxing'] == '木'
    assert t['to'] == '偏印格'
    assert '月令合局触发格局质变' in out['primaryReason']


GOLDEN_TRANSMUTATION_CASES = [
    {
        'label': '辛金亥月_亥卯未三合',
        'input': dict(year=1980, month=11, day=14, hour=14, minute=0,
                      gender='male', city='北京'),
        'trigger_type': 'sanHe',
        'trigger_wuxing': '木',
        'expected_to': '偏财格',
    },
    {
        'label': '乙木子月_申子辰三合',
        'input': dict(year=1992, month=12, day=15, hour=8, minute=0,
                      gender='female', city='上海'),
        'trigger_type': 'sanHe',
        'trigger_wuxing': '水',
        'expected_to': '偏印格',
    },
    {
        'label': '甲木午月_寅午戌三合',
        'input': dict(year=1980, month=6, day=10, hour=20, minute=0,
                      gender='male', city='北京'),
        'trigger_type': 'sanHe',
        'trigger_wuxing': '火',
        'expected_to': '伤官格',
    },
    {
        'label': '乙木寅月_寅卯辰三会',
        'input': dict(year=1980, month=2, day=12, hour=8, minute=0,
                      gender='male', city='北京'),
        'trigger_type': 'sanHui',
        'trigger_wuxing': '木',
        'expected_to': '比肩格',
    },
    {
        'label': '壬水巳月_巳午未三会',
        'input': dict(year=1980, month=5, day=9, hour=14, minute=0,
                      gender='male', city='北京'),
        'trigger_type': 'sanHui',
        'trigger_wuxing': '火',
        'expected_to': '正财格',
    },
]


@pytest.mark.parametrize(
    'case',
    GOLDEN_TRANSMUTATION_CASES,
    ids=[c['label'] for c in GOLDEN_TRANSMUTATION_CASES],
)
def test_yongshen_transmutation_golden(case):
    """Plan 7.5a §6.2: real charts trigger transmutation as expected."""
    out = compute(**case['input'])
    detail = out['yongshenDetail']
    transmuted = detail.get('transmuted')
    assert transmuted is not None, f"{case['label']}: expected transmuted, got None"
    assert transmuted['trigger']['type'] == case['trigger_type']
    assert transmuted['trigger']['wuxing'] == case['trigger_wuxing']
    assert transmuted['to'] == case['expected_to']
    cand = transmuted['candidate']
    assert cand['method'] == '格局'
    assert cand.get('name')
    assert cand.get('source', '').startswith('子平真诠')
    assert '月令合局触发格局质变' in detail['primaryReason']


def test_transmuted_from_uses_geju_key_not_candidate_name():
    """Plan 7.5a.1 §5.1 — transmuted.from 用真格局名 (post-alias).

    Before fix: from = '劫财（自立）' (candidate name from GEJU_RULES rule).
    After fix:  from = '劫财格' (GEJU_RULES key, post-alias from analyzer's '月刃格').
    """
    out = compute(year=1980, month=2, day=12, hour=8, minute=0,
                   gender='male', city='北京')
    detail = out['yongshenDetail']
    transmuted = detail.get('transmuted')
    assert transmuted is not None, '1980-02-12 案例应触发 transmutation'
    # from 应是格局名 (e.g. '劫财格' or '比肩格'), 不是 candidate name
    assert transmuted['from'].endswith('格'), \
        f"from='{transmuted['from']}' should end with '格'"
    assert '（' not in transmuted['from'], \
        f"from='{transmuted['from']}' should not contain '（' (candidate name marker)"
    # to 也是格局名 — 验证 from/to 同命名空间
    assert transmuted['to'].endswith('格')


GOLDEN_YONGSHEN_CASES = [
    {
        'label': '丁火六月_身弱_食神格',
        'input': dict(year=1993, month=7, day=15, hour=14, minute=30,
                      gender='male', city='长沙'),
        'expect': {
            'has_tiaohou': True,
            'has_geju': True,
            'tiaohou_source_contains': '穷通宝鉴',
            'geju_source_contains': '子平真诠',
        },
    },
    {
        'label': '丙火五月_身强',
        'input': dict(year=1990, month=5, day=12, hour=12, minute=0,
                      gender='male', city='北京'),
        'expect': {
            'has_tiaohou': True,
            'primary_not_empty': True,
        },
    },
    {
        'label': '甲木八月',
        'input': dict(year=2003, month=8, day=29, hour=8, minute=27,
                      gender='male', city='上海'),
        'expect': {'has_tiaohou': True},
    },
    {
        'label': '癸水正月',
        'input': dict(year=1985, month=1, day=5, hour=23, minute=45,
                      gender='female', city='广州'),
        'expect': {'has_tiaohou': True},
    },
    {
        'label': '辛金腊月',
        'input': dict(year=1976, month=11, day=30, hour=6, minute=15,
                      gender='female', city='成都'),
        'expect': {'has_tiaohou': True},
    },
    {
        'label': '戊土三月',
        'input': dict(year=2000, month=2, day=29, hour=16, minute=0,
                      gender='male', city='深圳'),
        'expect': {'has_tiaohou': True},
    },
    {
        'label': '丁火_寅午戌_三合',
        'input': dict(year=1984, month=10, day=5, hour=14, minute=0,
                      gender='male', city='北京'),
        'expect': {'primary_not_empty': True},
    },
    {
        'label': '乙木_寅卯辰_三会',
        'input': dict(year=1995, month=3, day=21, hour=12, minute=0,
                      gender='female', city='上海'),
        'expect': {'primary_not_empty': True},
    },
    {
        'label': '日主合化',
        'input': dict(year=1988, month=6, day=10, hour=9, minute=0,
                      gender='male', city='北京'),
        'expect': {'primary_not_empty': True},
    },
    {
        'label': '从格疑似',
        'input': dict(year=1974, month=8, day=8, hour=8, minute=0,
                      gender='female', city='昆明'),
        'expect': {'primary_not_empty': True},
    },
]


@pytest.mark.parametrize('case', GOLDEN_YONGSHEN_CASES,
                         ids=[c['label'] for c in GOLDEN_YONGSHEN_CASES])
def test_yongshen_golden(case):
    """Plan 7.3 §8.2: 10 golden cases assert structural soundness on real charts."""
    out = compute(**case['input'])
    detail = out.get('yongshenDetail')
    assert detail, f"{case['label']}: missing yongshenDetail"
    expect = case['expect']

    if expect.get('primary_not_empty'):
        assert detail['primary'], f"{case['label']}: primary is empty"

    if expect.get('has_tiaohou'):
        tiaohou = next(c for c in detail['candidates'] if c['method'] == '调候')
        assert tiaohou['name'], \
            f"{case['label']}: expected 调候 candidate (got name={tiaohou['name']!r})"

    if expect.get('has_geju'):
        geju = next(c for c in detail['candidates'] if c['method'] == '格局')
        assert geju['name'], \
            f"{case['label']}: expected 格局 candidate (got name={geju['name']!r})"

    if 'tiaohou_source_contains' in expect:
        tiaohou = next(c for c in detail['candidates'] if c['method'] == '调候')
        assert expect['tiaohou_source_contains'] in (tiaohou.get('source') or ''), \
            f"{case['label']}: 调候 source missing token"

    if 'geju_source_contains' in expect:
        geju = next(c for c in detail['candidates'] if c['method'] == '格局')
        assert expect['geju_source_contains'] in (geju.get('source') or ''), \
            f"{case['label']}: 格局 source missing token"
