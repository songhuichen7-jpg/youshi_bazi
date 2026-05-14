"""Plan 7.3 §6.3 — compact_chart_context renders 用神 block."""
from __future__ import annotations

from app.prompts.context import compact_chart_context


def _sample_paipan(yongshen_detail=None):
    return {
        'sizhu': {'year': '癸酉', 'month': '己未', 'day': '丁酉', 'hour': '丁未'},
        'rizhu': '丁',
        'yongshen': '庚金',
        'yongshenDetail': yongshen_detail,
    }


def test_renders_用神_block_when_detail_present():
    detail = {
        'primary': '庚金',
        'primaryReason': '调候 + 格局共指',
        'candidates': [
            {'method': '调候', 'name': '庚金', 'note': '丁火生未月', 'source': '穷通宝鉴·论丁火·六月'},
            {'method': '格局', 'name': '印（化杀）', 'note': '七杀透干', 'source': '子平真诠·论七杀'},
            {'method': '扶抑', 'name': '印 / 比劫', 'note': '身弱', 'source': '滴天髓·衰旺'},
        ],
        'warnings': [],
    }
    text = compact_chart_context(_sample_paipan(detail))
    assert '用神：庚金' in text
    assert '调候 + 格局共指' in text
    assert '调候 ▸ 庚金' in text
    assert '穷通宝鉴·论丁火·六月' in text
    assert '格局 ▸ 印（化杀）' in text
    assert '子平真诠·论七杀' in text
    assert '扶抑 ▸ 印 / 比劫' in text


def test_renders_warning_lines_with_prefix():
    detail = {
        'primary': '庚金',
        'primaryReason': '以调候为主',
        'candidates': [
            {'method': '调候', 'name': '庚金', 'note': '', 'source': '穷通宝鉴'},
            {'method': '格局', 'name': '印（化杀）', 'note': '', 'source': '子平真诠'},
            {'method': '扶抑', 'name': None, 'note': '', 'source': ''},
        ],
        'warnings': ['调候用神与格局用神不同 —— 古籍两派各有取法'],
    }
    text = compact_chart_context(_sample_paipan(detail))
    assert '⚠ 调候用神与格局用神不同' in text


def test_skips_block_when_yongshen_detail_absent():
    """No yongshenDetail → no 用神 line at all."""
    paipan = _sample_paipan(yongshen_detail=None)
    text = compact_chart_context(paipan)
    assert '用神：' not in text


def test_renders_em_dash_for_methods_without_name():
    detail = {
        'primary': '中和（无明显偏枯）',
        'primaryReason': '三法皆无强候选',
        'candidates': [
            {'method': '调候', 'name': None, 'note': '本月调候不强烈', 'source': ''},
            {'method': '格局', 'name': None, 'note': '格局未定或无规则', 'source': ''},
            {'method': '扶抑', 'name': None, 'note': '中和', 'source': ''},
        ],
        'warnings': [],
    }
    text = compact_chart_context(_sample_paipan(detail))
    assert '用神：中和' in text
    assert '本月调候不强烈' in text
    assert '中和' in text


def test_renders_transmuted_block_when_present():
    """Plan 7.5a §5.3: transmuted block renders with ⟳ glyph + new candidate line."""
    detail = {
        'primary': '甲木',
        'primaryReason': '以调候为主（注：月令合局触发格局质变，详见 transmuted 字段）',
        'candidates': [
            {'method': '调候', 'name': '甲木', 'note': '...', 'source': '穷通宝鉴·论丁火·六月'},
            {'method': '格局', 'name': '财（食神生财）', 'note': '...', 'source': '子平真诠·论食神'},
            {'method': '扶抑', 'name': '印 / 比劫', 'note': '...', 'source': '滴天髓·衰旺'},
        ],
        'warnings': [],
        'transmuted': {
            'trigger': {
                'type': 'sanHe', 'wuxing': '木', 'main': '卯',
                'zhi_list': ['亥', '卯', '未'], 'source': '三合亥卯未局',
            },
            'from': '正官格',
            'to': '偏印格',
            'candidate': {
                'method': '格局', 'name': '官（官印相生）',
                'sub_pattern': '官印相生', 'note': '偏印得官杀生',
                'source': '子平真诠·论印绶',
            },
            'warning': None,
            'alternateTriggers': [],
        },
    }
    paipan = {
        'sizhu': {'year': '癸酉', 'month': '己未', 'day': '丁酉', 'hour': '丁未'},
        'rizhu': '丁',
        'yongshen': '甲木',
        'yongshenDetail': detail,
    }
    text = compact_chart_context(paipan)
    assert '⟳ 月令变化' in text
    assert '正官格 → 偏印格' in text
    assert '三合亥卯未局' in text
    assert '格局新候选：官（官印相生）' in text
    assert '偏印得官杀生' in text
    assert '子平真诠·论印绶' in text


def test_renders_transmuted_warning_line():
    """Plan 7.5a §4.1: when warning present, ⚠ line appears under transmuted block."""
    detail = {
        'primary': '甲木',
        'primaryReason': '以调候为主（注：月令合局触发格局质变…）',
        'candidates': [
            {'method': '调候', 'name': '甲木', 'note': '', 'source': ''},
            {'method': '格局', 'name': '正官', 'note': '', 'source': ''},
            {'method': '扶抑', 'name': '印', 'note': '', 'source': ''},
        ],
        'warnings': [],
        'transmuted': {
            'trigger': {
                'type': 'sanHe', 'wuxing': '木', 'main': '卯',
                'zhi_list': ['亥', '卯', '未'], 'source': '三合亥卯未局',
            },
            'from': '正官格',
            'to': '偏印格',
            'candidate': {
                'method': '格局', 'name': '官（官印相生）',
                'note': '', 'source': '子平真诠·论印绶',
            },
            'warning': '月令合局后格局质变，原本"正官格"的取用法不再适用',
            'alternateTriggers': [],
        },
    }
    paipan = {
        'sizhu': {'year': '癸酉', 'month': '己未', 'day': '丁酉', 'hour': '丁未'},
        'rizhu': '丁',
        'yongshen': '甲木',
        'yongshenDetail': detail,
    }
    text = compact_chart_context(paipan)
    assert '月令合局后格局质变' in text
    assert '⚠' in text   # warning line glyph
