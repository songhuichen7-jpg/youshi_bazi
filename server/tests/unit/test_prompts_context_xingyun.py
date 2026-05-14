"""Plan 7.4 §6.2 — compact_chart_context renders 行运 block."""
from __future__ import annotations

from app.prompts.context import compact_chart_context


def _sample_paipan(xingyun=None):
    return {
        'sizhu': {'year': '癸酉', 'month': '己未', 'day': '丁酉', 'hour': '丁未'},
        'rizhu': '丁',
        'yongshen': '甲木',
        'yongshenDetail': {
            'primary': '甲木',
            'primaryReason': '以调候为主',
            'candidates': [],
            'warnings': [],
        },
        'xingyun': xingyun,
    }


def _make_xingyun_with_label(label='喜'):
    """Build a synthetic xingyun dict with 8 大运 (indices 1..8 to match real
    lunar-python data) and 10 流年 each. currentDayunIndex=4 (mid-range)."""
    return {
        'yongshenSnapshot': '甲木',
        'currentDayunIndex': 4,
        'dayun': [
            {'index': i, 'ganzhi': f'X{i}', 'startAge': 4 + (i-1)*10,
             'startYear': 1997 + (i-1)*10, 'endYear': 2006 + (i-1)*10,
             'label': label, 'score': 2,
             'note': f'测试note{i}', 'mechanisms': [], 'isCurrent': i == 4}
            for i in range(1, 9)
        ],
        'liunian': {
            str(i): [
                {'year': 1997 + (i-1)*10 + j, 'ganzhi': f'L{j}', 'age': 5 + (i-1)*10 + j,
                 'label': '平', 'score': 0,
                 'note': f'流年{j}', 'mechanisms': []}
                for j in range(10)
            ]
            for i in range(1, 9)
        },
    }


def test_renders_行运_block_when_xingyun_present():
    xy = _make_xingyun_with_label('喜')
    text = compact_chart_context(_sample_paipan(xy))
    assert '行运（对照命局用神 甲木）' in text
    # All 8 大运 appear
    for i in range(1, 9):
        assert f'X{i}' in text


def test_renders_star_marker_for_current_dayun():
    xy = _make_xingyun_with_label('喜')
    text = compact_chart_context(_sample_paipan(xy))
    # ★ should appear on the current dayun (index 4, ganzhi X4 — 1-indexed real data)
    lines = text.splitlines()
    star_lines = [l for l in lines if '★' in l and 'X4' in l]
    assert len(star_lines) == 1, f'expected one star line on X4, found {star_lines}'


def test_renders_glyph_for_each_label_bin():
    """Build xingyun with a different label per dayun and verify each glyph appears."""
    labels_in_order = ['大喜', '喜', '平', '忌', '大忌', '喜', '平', '喜']
    xy = _make_xingyun_with_label('喜')
    for i, lbl in enumerate(labels_in_order):
        xy['dayun'][i]['label'] = lbl
    text = compact_chart_context(_sample_paipan(xy))
    # All 5 distinct glyphs should appear
    for glyph in ['⭐⭐', '⭐', '·', '⚠', '⚠⚠']:
        assert glyph in text, f'glyph {glyph!r} missing from rendered text'


def test_skips_block_when_xingyun_absent():
    """No xingyun → no 行运 line at all."""
    paipan = _sample_paipan(xingyun=None)
    text = compact_chart_context(paipan)
    assert '行运（' not in text


def test_skips_block_when_xingyun_dayun_empty_中和():
    """中和 命局 → all-平 collapse → no 行运 block."""
    xy = {
        'yongshenSnapshot': '中和（无明显偏枯）',
        'currentDayunIndex': None,
        'dayun': [],
        'liunian': {},
    }
    paipan = _sample_paipan(xy)
    text = compact_chart_context(paipan)
    assert '行运（' not in text


def test_renders_xingyun_dayun_transmuted_block():
    """Plan 7.5b §5.3: dayun entry with transmuted renders ⟳ block."""
    xy = _make_xingyun_with_label('喜')
    # Inject transmuted into 大运 4 (current)
    xy['dayun'][3]['transmuted'] = {
        'trigger': {
            'type': 'sanHe', 'wuxing': '木', 'main': '卯',
            'zhi_list': ['亥', '卯', '未'], 'source': '三合亥卯未局',
        },
        'from': '正官格',
        'to': '偏印格',
        'candidate': {
            'method': '格局', 'name': '官（官印相生）',
            'note': '偏印得官杀生', 'source': '子平真诠·论印绶',
        },
        'warning': None,
        'alternateTriggers': [],
    }
    paipan = _sample_paipan(xy)
    text = compact_chart_context(paipan)
    assert '⟳ 月令变化' in text
    assert '正官格 → 偏印格' in text
    assert '三合亥卯未局' in text
    assert '格局新候选：官（官印相生）' in text


def test_renders_xingyun_liunian_transmuted_block():
    """Plan 7.5b §5.3: liunian entry with transmuted renders ⟳ block (deeper indent)."""
    xy = _make_xingyun_with_label('喜')
    cur_idx = xy['currentDayunIndex']
    # Inject transmuted into liunian[cur_idx][2]
    xy['liunian'][str(cur_idx)][2]['transmuted'] = {
        'trigger': {
            'type': 'sanHui', 'wuxing': '水', 'main': '子',
            'zhi_list': ['亥', '子', '丑'], 'source': '三会北方',
        },
        'from': '正财格',
        'to': '七杀格',
        'candidate': {
            'method': '格局', 'name': '食神（制杀）',
            'note': '...', 'source': '子平真诠·论偏官',
        },
        'warning': '...',
        'alternateTriggers': [],
    }
    paipan = _sample_paipan(xy)
    text = compact_chart_context(paipan)
    assert '三会北方' in text
    assert '正财格 → 七杀格' in text
