"""Plan 7.3 — yongshen_data table schema validity."""
from __future__ import annotations

import pytest

from paipan.yongshen_data import TIAOHOU, GEJU_RULES, FUYI_CASES


# All 10 day masters
ALL_GANS = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
# All 12 months by 地支
ALL_MONTH_ZHIS = ['寅', '卯', '辰', '巳', '午', '未',
                   '申', '酉', '戌', '亥', '子', '丑']


def test_tiaohou_covers_all_120_pairs():
    """Plan 7.3 §4.1: TIAOHOU should have all 10 × 12 = 120 entries."""
    for gan in ALL_GANS:
        for zhi in ALL_MONTH_ZHIS:
            assert (gan, zhi) in TIAOHOU, f"missing TIAOHOU[({gan},{zhi})]"


def test_tiaohou_entries_have_required_fields():
    for key, entry in TIAOHOU.items():
        assert 'name' in entry, f"TIAOHOU[{key}] missing 'name'"
        assert 'note' in entry, f"TIAOHOU[{key}] missing 'note'"
        assert 'source' in entry, f"TIAOHOU[{key}] missing 'source'"
        # source must point to 穷通宝鉴
        assert '穷通宝鉴' in entry['source'], \
            f"TIAOHOU[{key}].source should cite 穷通宝鉴, got {entry['source']!r}"


def test_tiaohou_note_length_reasonable():
    """Notes should be concise (≤ 60 chars after Plan 7.3 spec §4.1 ~30字)."""
    for key, entry in TIAOHOU.items():
        note = entry.get('note', '')
        assert len(note) <= 60, \
            f"TIAOHOU[{key}].note too long ({len(note)} chars): {note!r}"


def test_geju_rules_each_格局_has_at_least_one_default():
    """Each 格局 with rules must have a final 'condition: lambda ...: True' default."""
    for geju, rules in GEJU_RULES.items():
        if not rules:
            continue   # 格局不清 is intentionally empty
        last = rules[-1]
        assert callable(last.get('condition')), \
            f"{geju} last rule missing condition"
        # Default rule should accept anything: simulate with empty force/gan_he
        assert last['condition']({'scores': {}}, {}) is True, \
            f"{geju} last rule should be a default (always True)"


def test_geju_rules_entries_have_required_fields():
    for geju, rules in GEJU_RULES.items():
        for i, rule in enumerate(rules):
            assert 'condition' in rule, f"{geju}[{i}] missing condition"
            assert callable(rule['condition'])
            assert 'name' in rule, f"{geju}[{i}] missing name"
            assert 'source' in rule, f"{geju}[{i}] missing source"
            assert '子平真诠' in rule['source'], \
                f"{geju}[{i}].source should cite 子平真诠"


def test_fuyi_cases_cover_all_5_dayStrength_values():
    """Each of {极弱, 身弱, 中和, 身强, 极强} should match exactly one case."""
    expected = {'极弱', '身弱', '中和', '身强', '极强'}
    seen = set()
    for ds in expected:
        for case in FUYI_CASES:
            if case['when']({'scores': {}}, ds):
                seen.add(ds)
                break
    assert seen == expected, f"missing: {expected - seen}"


def test_fuyi_cases_entries_have_required_fields():
    for i, case in enumerate(FUYI_CASES):
        assert 'when' in case and callable(case['when']), \
            f"FUYI_CASES[{i}] missing or non-callable when"
        assert 'name' in case, f"FUYI_CASES[{i}] missing name (None allowed)"
        assert 'note' in case, f"FUYI_CASES[{i}] missing note"
        assert 'source' in case, f"FUYI_CASES[{i}] missing source"
