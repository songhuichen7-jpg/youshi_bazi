"""Plan 7.3 — 用神 engine.

Public API:
  build_yongshen(
      rizhu_gan, month_zhi, force, geju, gan_he, day_strength,
      mingju_zhis=None,
  ) -> dict

Returns a dict with shape:
  {
    'primary': '<one-line label, e.g. "庚金 / 丁火">',
    'primaryReason': '<why this is primary>',
    'candidates': [
      {'method': '调候'|'格局'|'扶抑', 'name': str|None,
       'note': str, 'source': str, ...},
      ...
    ],
    'warnings': [str, ...]   # may be empty
  }

Spec: docs/superpowers/specs/2026-04-20-yongshen-engine-design.md
"""
from __future__ import annotations

from paipan.cang_gan import get_ben_qi
from paipan.ganzhi import GAN_WUXING, GAN_YINYANG, WUXING_KE, WUXING_SHENG
from paipan.he_ke import SAN_HE_JU, SAN_HUI
from paipan.yongshen_data import TIAOHOU, GEJU_RULES, FUYI_CASES


# Plan 7.5a §3.3 — 10 entries; 5 十神类 × 2 阴阳 polarity
_GEJU_NAME_TABLE: dict[tuple[str, str], str] = {
    ('印', 'same'):     '偏印格',
    ('印', 'opposite'): '正印格',
    ('比劫', 'same'):     '比肩格',
    ('比劫', 'opposite'): '劫财格',
    ('食伤', 'same'):     '食神格',
    ('食伤', 'opposite'): '伤官格',
    ('财', 'same'):     '偏财格',
    ('财', 'opposite'): '正财格',
    ('官杀', 'same'):     '七杀格',
    ('官杀', 'opposite'): '正官格',
}

_GEJU_ALIASES = {
    '建禄格': '比肩格',
    '月刃格': '劫财格',
    '阳刃格': '劫财格',
}


def _compute_virtual_geju_name(
    new_wuxing: str,
    rizhu_gan: str,
    main_zhi: str,
) -> str | None:
    """五行 + 日主 + main支 → 格局名 (10种之一)。

    Algorithm (spec §3.3):
      1. 算 ten_god_class (印/比劫/食伤/财/官杀) by new_wuxing vs rizhu_wx
      2. 算 polarity (same/opposite) by main_zhi 本气阴阳 vs rizhu_gan 阴阳
      3. lookup _GEJU_NAME_TABLE[(ten_god_class, polarity)]
    """
    rizhu_wx = GAN_WUXING.get(rizhu_gan)
    rizhu_yy = GAN_YINYANG.get(rizhu_gan)
    if not rizhu_wx or not rizhu_yy:
        return None

    main_gan = get_ben_qi(main_zhi)
    main_yy = GAN_YINYANG.get(main_gan)
    if not main_yy:
        return None

    if new_wuxing == rizhu_wx:
        ten_god_class = '比劫'
    elif WUXING_SHENG.get(new_wuxing) == rizhu_wx:
        ten_god_class = '印'
    elif WUXING_SHENG.get(rizhu_wx) == new_wuxing:
        ten_god_class = '食伤'
    elif WUXING_KE.get(rizhu_wx) == new_wuxing:
        ten_god_class = '财'
    elif WUXING_KE.get(new_wuxing) == rizhu_wx:
        ten_god_class = '官杀'
    else:
        return None  # 不应触发，但兜底

    polarity = 'same' if main_yy == rizhu_yy else 'opposite'
    return _GEJU_NAME_TABLE.get((ten_god_class, polarity))


def _detect_transmutation(
    month_zhi: str,
    mingju_zhis: list[str],
    rizhu_gan: str,
    force: dict,
    gan_he: dict,
    *,
    original_geju_name: str = '',
    tiaohou_candidate: dict | None = None,
) -> dict | None:
    """Detect 命局自带 三合/三会 + 月令参与, return transmuted dict or None.

    See spec §3.3 for trigger algorithm + §3.4 for warning rules + §4 for output shape.
    """
    candidate_combos: list[dict] = []

    # 三合 (4 种)
    for ju in SAN_HE_JU:
        matched = [z for z in ju["zhi"] if z in mingju_zhis]
        if month_zhi in matched and len(matched) == 3:
            candidate_combos.append({
                'type': 'sanHe',
                'wuxing': ju["wx"],
                'main': ju["main"],
                'zhi_list': list(ju["zhi"]),
                'source': f"三合{''.join(ju['zhi'])}局",
            })

    # 三会 (4 种)
    for hui in SAN_HUI:
        matched = [z for z in hui["zhi"] if z in mingju_zhis]
        if month_zhi in matched and len(matched) == 3:
            candidate_combos.append({
                'type': 'sanHui',
                'wuxing': hui["wx"],
                'main': hui["zhi"][1],
                'zhi_list': list(hui["zhi"]),
                'source': f"三会{hui['dir']}方",
            })

    if not candidate_combos:
        return None

    # 优先级 (spec §3.3): 三合 > 三会; 同型按出现顺序
    candidate_combos.sort(key=lambda c: 0 if c['type'] == 'sanHe' else 1)
    chosen = candidate_combos[0]
    alternates = candidate_combos[1:]

    # 计算虚拟格局名
    virtual_geju_name = _compute_virtual_geju_name(
        chosen['wuxing'], rizhu_gan, chosen['main']
    )
    if not virtual_geju_name:
        return None

    # 重算格局法 用神 (复用 Plan 7.3 geju_yongshen)
    new_candidate = geju_yongshen(virtual_geju_name, force, gan_he)
    if new_candidate is None:
        # GEJU_RULES 应该全覆盖 10 个格局名 (spec §3.4 risk #1 已 frozen)
        # 但兜底防御
        return None

    # warning (spec §4.1)
    warning: str | None = None
    tiaohou_name = (tiaohou_candidate or {}).get('name', '') if tiaohou_candidate else ''
    new_cand_name = new_candidate.get('name', '')
    if tiaohou_name and new_cand_name and tiaohou_name == new_cand_name:
        warning = None  # 调候 + 转化后格局 一致
    elif new_cand_name != original_geju_name:
        warning = f"月令合局后格局质变，原本\"{original_geju_name or '?'}\"的取用法不再适用"

    return {
        'trigger': chosen,
        'from': original_geju_name or '?',
        'to': virtual_geju_name,
        'candidate': new_candidate,
        'warning': warning,
        'alternateTriggers': alternates,
    }


def tiaohou_yongshen(rizhu_gan: str, month_zhi: str) -> dict | None:
    """Return TIAOHOU entry or None if not strongly indicated."""
    entry = TIAOHOU.get((rizhu_gan, month_zhi))
    if not entry or not entry.get('name'):
        return None
    return {
        'method': '调候',
        'name': entry['name'],
        'supporting': entry.get('supporting'),
        'note': entry.get('note', ''),
        'source': entry.get('source', '穷通宝鉴'),
    }


def geju_yongshen(geju: str | None, force: dict, gan_he: dict) -> dict | None:
    """Return first matching GEJU_RULES entry or None if 格局 unknown/unclear."""
    if not geju:
        return None
    normalized_geju = _GEJU_ALIASES.get(geju, geju)
    rules = GEJU_RULES.get(normalized_geju, [])
    for rule in rules:
        cond = rule.get('condition')
        if cond and cond(force, gan_he):
            return {
                'method': '格局',
                'name': rule['name'],
                'sub_pattern': rule.get('sub_pattern'),
                'note': rule.get('note', ''),
                'source': rule.get('source', '子平真诠'),
            }
    return None


def fuyi_yongshen(force: dict, day_strength: str | None) -> dict | None:
    """Return matching FUYI_CASES entry or None for 中和."""
    if not day_strength:
        return None
    for case in FUYI_CASES:
        when = case.get('when')
        if when and when(force, day_strength):
            if case.get('name') is None:
                return None
            return {
                'method': '扶抑',
                'name': case['name'],
                'note': case.get('note', ''),
                'source': case.get('source', '滴天髓·衰旺'),
            }
    return None


def _empty_candidate(method: str, note: str = '本法无明确结论') -> dict:
    return {'method': method, 'name': None, 'note': note, 'source': ''}


def compose_yongshen(
    tiaohou: dict | None,
    geju: dict | None,
    fuyi: dict | None,
) -> dict:
    """Compose 3 candidates into final dict per spec §3.2.

    Composition rule:
      - 调候 == 格局 → primary = 调候.name, no warning
      - 调候 != 格局 (both present) → primary = 调候.name, warning '古籍两派各有取法'
      - only 格局 → primary = 格局.name
      - only 扶抑 → primary = 扶抑.name
      - none → primary = '中和（无明显偏枯）'
    """
    candidates = [
        tiaohou or _empty_candidate('调候', '本月调候不强烈'),
        geju or _empty_candidate('格局', '格局未定或无规则'),
        fuyi or _empty_candidate('扶抑', '中和'),
    ]
    warnings: list[str] = []

    if tiaohou and geju:
        if _names_match(tiaohou.get('name'), geju.get('name')):
            primary = tiaohou['name']
            primary_reason = '调候 + 格局共指'
        else:
            primary = tiaohou['name']
            primary_reason = '以调候为主'
            warnings.append('调候用神与格局用神不同 —— 古籍两派各有取法')
    elif tiaohou:
        primary = tiaohou['name']
        primary_reason = '调候法'
    elif geju:
        primary = geju['name']
        primary_reason = '格局法'
    elif fuyi:
        primary = fuyi['name']
        primary_reason = '扶抑法（前两法无明确结论）'
    else:
        primary = '中和（无明显偏枯）'
        primary_reason = '三法皆无强候选'

    return {
        'primary': primary,
        'primaryReason': primary_reason,
        'candidates': candidates,
        'warnings': warnings,
    }


def _names_match(a: str | None, b: str | None) -> bool:
    """Loose name match. v1 just exact-match. v1.5 may add wuxing equivalence."""
    if not a or not b:
        return False
    return a == b


def build_yongshen(
    rizhu_gan: str,
    month_zhi: str | None,
    force: dict,
    geju: str | None,
    gan_he: dict,
    day_strength: str | None,
    mingju_zhis: list[str] | None = None,
) -> dict:
    """Top-level 用神 engine entry point. Composes 3 methods + optional transmutation."""
    tiaohou = tiaohou_yongshen(rizhu_gan, month_zhi) if month_zhi else None
    geju_res = geju_yongshen(geju, force, gan_he)
    fuyi_res = fuyi_yongshen(force, day_strength)
    composed = compose_yongshen(tiaohou, geju_res, fuyi_res)

    if mingju_zhis and month_zhi:
        original_geju_name = _GEJU_ALIASES.get(geju, geju) if geju else ''
        tiaohou_candidate = next(
            (c for c in composed['candidates'] if c.get('method') == '调候'),
            None,
        )
        transmuted = _detect_transmutation(
            month_zhi,
            mingju_zhis,
            rizhu_gan,
            force,
            gan_he,
            original_geju_name=original_geju_name,
            tiaohou_candidate=tiaohou_candidate,
        )
        if transmuted:
            composed['transmuted'] = transmuted
            composed['primaryReason'] = (
                (composed.get('primaryReason') or '')
                + '（注：月令合局触发格局质变，详见 transmuted 字段）'
            )

    return composed
