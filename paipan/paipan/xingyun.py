"""Plan 7.4 — 行运 scoring engine.

Public API:
  score_yun(yun_ganzhi, yongshen_primary, mingju_gans, mingju_zhis) -> dict
  build_xingyun(dayun, yongshen_detail, mingju_gans, mingju_zhis, current_year) -> dict

Spec: docs/superpowers/specs/2026-04-20-xingyun-engine-design.md
"""
from __future__ import annotations

from paipan import mechanism_tags as M
from paipan.ganzhi import (
    GAN_WUXING,
    ZHI_WUXING,
    WUXING_SHENG,
    WUXING_KE,
    split_ganzhi,
)
from paipan.xingyun_data import (
    GAN_HE_TABLE,
    ZHI_LIUHE_TABLE,
    SCORE_THRESHOLDS,
    YONGSHEN_WEIGHTS,
)
from paipan.yongshen import _detect_transmutation


def _is_same_combo(a: dict | None, b: dict | None) -> bool:
    """Plan 7.5b §3.3 — Compare two transmuted dicts for same trigger combo.

    True iff both non-None AND trigger.type + zhi_list (as set) match.
    Used for dedup: 大运 transmuted vs 命局-only baseline; 流年 vs 大运.
    """
    if not a or not b:
        return False
    if a['trigger']['type'] != b['trigger']['type']:
        return False
    return set(a['trigger']['zhi_list']) == set(b['trigger']['zhi_list'])


def _detect_xingyun_transmutation(
    month_zhi: str,
    base_mingju_zhis: list[str],
    dayun_zhi: str,
    liunian_zhi: str | None,
    *,
    rizhu_gan: str,
    force: dict,
    gan_he: dict,
    original_geju_name: str,
    baseline_transmuted: dict | None = None,
) -> dict | None:
    """Detect 大运/流年 transmutation with dedup. Spec §3.3.

    Args:
        month_zhi: 月令地支
        base_mingju_zhis: 命局 4 支
        dayun_zhi: 大运地支
        liunian_zhi: 流年地支 (None for 大运 entry detection)
        rizhu_gan/force/gan_he/original_geju_name: passed through to _detect_transmutation
        baseline_transmuted: 大运 entry's already-computed transmuted (for 流年 dedup)

    Returns transmuted dict or None.
    """
    if liunian_zhi is None:
        # 大运 entry: dedup against 命局-only baseline
        with_dayun = _detect_transmutation(
            month_zhi,
            base_mingju_zhis + [dayun_zhi],
            rizhu_gan, force, gan_he,
            original_geju_name=original_geju_name,
        )
        if not with_dayun:
            return None
        baseline = _detect_transmutation(
            month_zhi, base_mingju_zhis,
            rizhu_gan, force, gan_he,
            original_geju_name=original_geju_name,
        )
        if _is_same_combo(with_dayun, baseline):
            return None
        return with_dayun
    else:
        # 流年 entry: dedup against 大运 transmuted
        with_liunian = _detect_transmutation(
            month_zhi,
            base_mingju_zhis + [dayun_zhi, liunian_zhi],
            rizhu_gan, force, gan_he,
            original_geju_name=original_geju_name,
        )
        if not with_liunian:
            return None
        if _is_same_combo(with_liunian, baseline_transmuted):
            return None
        return with_liunian


def _classify_score(score: int) -> str:
    """5-bin classifier per spec §3.4.

    Bins: >=4 大喜, 2-3 喜, -1..1 平, -3..-2 忌, <=-4 大忌
    """
    if score >= SCORE_THRESHOLDS['大喜']:
        return '大喜'
    if score >= SCORE_THRESHOLDS['喜']:
        return '喜'
    if score >= -1:
        return '平'
    if score >= -3:
        return '忌'
    return '大忌'


def _trim_note(note: str, limit: int = 30) -> str:
    """在 ≤ limit 字符内优先在中文标点边界截断 (Plan 7.5a.1 §5.4).

    优先级: 句末 (。) > 分句 (；：) > 子句 (，)
    回退: 字符级硬切（如果在 limit//2 之前就找到分隔符放弃，避免切得太短）

    Examples:
        _trim_note('丙生用神，午比助用神') → '丙生用神，午比助用神'  (短不变)
        _trim_note('丙生用神，午比助用神，但与命局丁壬合化木') → '丙生用神，午比助用神，'  (切到最后",")
        _trim_note('一二三，四五六七八九十一二三四五六七八九十一二三四五六七八九十') → '一二三四五六七八九十一二三四五六七八九十一二三四五六七八九十'[:30]  (",":idx=3 < 15, fallback)
    """
    if len(note) <= limit:
        return note
    for sep in ['。', '；', '：', '，']:
        idx = note.rfind(sep, 0, limit)
        if idx > limit // 2:
            return note[:idx + 1]
    return note[:limit]


def _extract_yongshen_wuxings(primary: str) -> list[str]:
    """Parse '甲木 / 戊土 / 庚金' → ['木', '土', '金'].

    Rules:
      - Split on ' / ' (with surrounding spaces, matches Plan 7.3 format)
      - For each element, the last char should be a 五行 (木/火/土/金/水)
      - If element is '中和（无明显偏枯）' or has no 五行 char → return []
        (caller treats this as 中和 命局, returns 平/empty per spec §3.3)
    """
    if not primary:
        return []
    if '中和' in primary:
        return []
    valid_wuxings = {'木', '火', '土', '金', '水'}
    parts = [p.strip() for p in primary.split(' / ')]
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        last_char = part[-1]
        if last_char in valid_wuxings:
            out.append(last_char)
        # else skip silently — primary may have unexpected formats
    return out


def _detect_ganhe(
    gan: str,
    mingju_gans: list[str],
    *,
    source_idx: int | None = None,
) -> str | None:
    """Detect 干合化.

    If source_idx is None, gan is external (大运/流年) and any position counts.
    If source_idx is given, gan is mingju_gans[source_idx] and only adjacent
    pairs count.
    """
    for idx, mg in enumerate(mingju_gans):
        if mg == gan:
            continue   # self-pair doesn't count
        if source_idx is not None and abs(idx - source_idx) != 1:
            continue
        wx = GAN_HE_TABLE.get(frozenset({gan, mg}))
        if wx:
            return wx
    return None


def _detect_liuhe(
    zhi: str,
    mingju_zhis: list[str],
    *,
    source_idx: int | None = None,
) -> str | None:
    """Detect 地支六合.

    If source_idx is None, zhi is external (大运/流年) and any position counts.
    If source_idx is given, zhi is mingju_zhis[source_idx] and only adjacent
    pairs count.
    """
    for idx, mz in enumerate(mingju_zhis):
        if mz == zhi:
            continue   # self-pair doesn't count
        if source_idx is not None and abs(idx - source_idx) != 1:
            continue
        wx = ZHI_LIUHE_TABLE.get(frozenset({zhi, mz}))
        if wx:
            return wx
    return None


def _score_gan_to_yongshen(
    gan: str, ys_wuxing: str, mingju_gans: list[str]
) -> tuple[int, str, list[str]]:
    """Score 大运/流年 干 against a single 用神 五行.

    Base scoring (per spec §3.3 step 2):
      - gan_wuxing == ys_wuxing → +1 (比助)
      - gan_wuxing 生 ys_wuxing → +2
      - ys_wuxing 生 gan_wuxing → -1 (用神被泄)
      - gan_wuxing 克 ys_wuxing → -2
      - ys_wuxing 克 gan_wuxing → 0 (中性)
      - else → 0

    干合化 modifier (spec §3.3):
      - 合化 五行 == ys_wuxing → +1
      - 合化 五行 生 ys_wuxing → +1
      - 合化 五行 克 ys_wuxing → -1

    Returns (delta, human-readable reason, list of structured mechanism tags).
    """
    gw = GAN_WUXING.get(gan)
    if gw is None:
        return (0, '未知干', [])

    base_delta = 0
    base_reason = ''
    base_mech: list[str] = []

    if gw == ys_wuxing:
        base_delta = 1
        base_reason = f'{gan}比助用神'
        base_mech.append(M.GAN_BIZHU)
    elif WUXING_SHENG.get(gw) == ys_wuxing:
        base_delta = 2
        base_reason = f'{gan}生用神'
        base_mech.append(M.GAN_SHENG)
    elif WUXING_SHENG.get(ys_wuxing) == gw:
        base_delta = -1
        base_reason = f'用神被{gan}泄'
        base_mech.append(M.GAN_XIE)
    elif WUXING_KE.get(gw) == ys_wuxing:
        base_delta = -2
        base_reason = f'{gan}克用神'
        base_mech.append(M.GAN_KE)
    elif WUXING_KE.get(ys_wuxing) == gw:
        base_delta = 0
        base_reason = f'用神克{gan}'
        # No mechanism tag for this — neutral

    # 干合化 modifier
    he_wx = _detect_ganhe(gan, mingju_gans)
    if he_wx:
        if he_wx == ys_wuxing or WUXING_SHENG.get(he_wx) == ys_wuxing:
            base_delta += 1
            base_reason += f'，与命局合化{he_wx}转助'
            base_mech.append(M.gan_hehua_zhuanzhu(he_wx))
        elif WUXING_KE.get(he_wx) == ys_wuxing:
            base_delta -= 1
            base_reason += f'，与命局合化{he_wx}反克'
            base_mech.append(M.gan_hehua_fanke(he_wx))

    return (base_delta, base_reason, base_mech)


def _score_zhi_to_yongshen(
    zhi: str, ys_wuxing: str, mingju_zhis: list[str]
) -> tuple[int, str, list[str]]:
    """Score 大运/流年 支 (本气五行) against a single 用神 五行.

    Logic mirrors _score_gan_to_yongshen but uses ZHI_WUXING for base 五行
    and ZHI_LIUHE_TABLE for the合化 modifier.

    Returns (delta, reason, mechanisms).
    """
    zw = ZHI_WUXING.get(zhi)
    if zw is None:
        return (0, '未知支', [])

    base_delta = 0
    base_reason = ''
    base_mech: list[str] = []

    if zw == ys_wuxing:
        base_delta = 1
        base_reason = f'{zhi}比助用神'
        base_mech.append(M.ZHI_BIZHU)
    elif WUXING_SHENG.get(zw) == ys_wuxing:
        base_delta = 2
        base_reason = f'{zhi}生用神'
        base_mech.append(M.ZHI_SHENG)
    elif WUXING_SHENG.get(ys_wuxing) == zw:
        base_delta = -1
        base_reason = f'用神被{zhi}泄'
        base_mech.append(M.ZHI_XIE)
    elif WUXING_KE.get(zw) == ys_wuxing:
        base_delta = -2
        base_reason = f'{zhi}克用神'
        base_mech.append(M.ZHI_KE)
    elif WUXING_KE.get(ys_wuxing) == zw:
        base_delta = 0
        base_reason = f'用神克{zhi}'

    # 六合 modifier
    he_wx = _detect_liuhe(zhi, mingju_zhis)
    if he_wx:
        if he_wx == ys_wuxing or WUXING_SHENG.get(he_wx) == ys_wuxing:
            base_delta += 1
            base_reason += f'，与命局六合化{he_wx}转助'
            base_mech.append(M.zhi_liuhe_zhuanzhu(he_wx))
        elif WUXING_KE.get(he_wx) == ys_wuxing:
            base_delta -= 1
            base_reason += f'，与命局六合化{he_wx}反克'
            base_mech.append(M.zhi_liuhe_fanke(he_wx))

    return (base_delta, base_reason, base_mech)


def score_yun(
    yun_ganzhi: str,
    yongshen_primary: str,
    mingju_gans: list[str],
    mingju_zhis: list[str],
) -> dict:
    """Score one 大运/流年 ganzhi against 命局 用神. Spec §5.1.

    Multi-element 用神: weighted-average sub-scores across elements.
    中和 命局: return label='平', score=0, empty mechanisms (spec §3.3).
    """
    ys_wuxings = _extract_yongshen_wuxings(yongshen_primary)
    if not ys_wuxings:
        return {
            'label': '平',
            'score': 0,
            'note': '命局中和，行运无明显偏向',
            'mechanisms': [],
            'gan_effect': {'delta': 0, 'reason': ''},
            'zhi_effect': {'delta': 0, 'reason': ''},
            'winningYongshenElement': None,
        }

    yun_gan, yun_zhi = split_ganzhi(yun_ganzhi)

    # Compute sub-score for each yongshen element.
    sub_results = []
    for ys_wx in ys_wuxings:
        gan_d, gan_r, gan_m = _score_gan_to_yongshen(yun_gan, ys_wx, mingju_gans)
        zhi_d, zhi_r, zhi_m = _score_zhi_to_yongshen(yun_zhi, ys_wx, mingju_zhis)
        total = gan_d + zhi_d
        sub_results.append((
            total,
            {'delta': gan_d, 'reason': gan_r, 'mech': gan_m},
            {'delta': zhi_d, 'reason': zhi_r, 'mech': zhi_m},
            ys_wx,
        ))

    n = len(sub_results)
    weights = YONGSHEN_WEIGHTS[:n]
    if weights and sum(weights) > 0:
        weights = [w / sum(weights) for w in weights]
        final_score_raw = sum(w * r[0] for w, r in zip(weights, sub_results))
        final_score = round(final_score_raw)
    else:
        final_score = 0

    # Keep explainability tied to the max sub-score element.
    best_idx = max(range(n), key=lambda i: sub_results[i][0]) if n > 0 else 0
    if n > 0:
        winning_wx = sub_results[best_idx][3]
        gan_eff = sub_results[best_idx][1]
        zhi_eff = sub_results[best_idx][2]
    else:
        winning_wx = ''
        gan_eff = {'delta': 0, 'reason': '', 'mech': []}
        zhi_eff = {'delta': 0, 'reason': '', 'mech': []}

    # Note: combine gan + zhi reason, comma-separated, ≤30 字
    parts = []
    if gan_eff['reason']:
        parts.append(gan_eff['reason'])
    if zhi_eff['reason']:
        parts.append(zhi_eff['reason'])
    note = '，'.join(parts) if parts else '无显著作用'
    note = _trim_note(note)

    mechanisms = list(gan_eff['mech']) + list(zhi_eff['mech'])

    # Find which yongshen element name matches winning_wx
    winning_element_name = None
    for elem in (yongshen_primary or '').split(' / '):
        elem = elem.strip()
        if elem and elem.endswith(winning_wx):
            winning_element_name = elem
            break

    return {
        'label': _classify_score(final_score),
        'score': final_score,
        'note': note,
        'mechanisms': mechanisms,
        'gan_effect': {'delta': gan_eff['delta'], 'reason': gan_eff['reason']},
        'zhi_effect': {'delta': zhi_eff['delta'], 'reason': zhi_eff['reason']},
        'winningYongshenElement': winning_element_name,
    }


def build_xingyun(
    dayun: dict,
    yongshen_detail: dict,
    mingju_gans: list[str],
    mingju_zhis: list[str],
    current_year: int,
    *,
    chart_context: dict | None = None,
) -> dict:
    """Batch entry. Spec §5.2.

    Iterates 8 大运 + each大运's 10 流年, scoring each via score_yun.
    Locates currentDayunIndex by which entry's [startYear, endYear]
    contains current_year (None if none match).
    """
    yongshen_primary = (yongshen_detail or {}).get('primary', '')
    if not _extract_yongshen_wuxings(yongshen_primary):
        return {
            'dayun': [], 'liunian': {},
            'currentDayunIndex': None,
            'yongshenSnapshot': yongshen_primary,
        }

    dayun_list = (dayun or {}).get('list', [])
    out_dayun: list[dict] = []
    out_liunian: dict[str, list[dict]] = {}
    current_idx: int | None = None

    for entry in dayun_list:
        idx = entry['index']
        ganzhi = entry['ganzhi']
        start_year = entry['startYear']
        end_year = entry['endYear']

        score = score_yun(ganzhi, yongshen_primary, mingju_gans, mingju_zhis)

        # Plan 7.5b: dayun-level transmutation detection
        dayun_transmuted = None
        if chart_context:
            dayun_transmuted = _detect_xingyun_transmutation(
                month_zhi=chart_context['month_zhi'],
                base_mingju_zhis=mingju_zhis,
                dayun_zhi=ganzhi[1],
                liunian_zhi=None,
                rizhu_gan=chart_context['rizhu_gan'],
                force=chart_context['force'],
                gan_he=chart_context['gan_he'],
                original_geju_name=chart_context['original_geju_name'],
            )

        out_dayun.append({
            'index': idx,
            'ganzhi': ganzhi,
            'startAge': entry['startAge'],
            'startYear': start_year,
            'endYear': end_year,
            'label': score['label'],
            'score': score['score'],
            'note': score['note'],
            'mechanisms': score['mechanisms'],
            'isCurrent': start_year <= current_year <= end_year,
            'transmuted': dayun_transmuted,    # NEW (Plan 7.5b)
        })

        if start_year <= current_year <= end_year:
            current_idx = idx

        # 流年 evaluations within this 大运
        ln_entries = []
        for ly in entry.get('liunian', []):
            # Plan 7.7: extend mingju with 当前大运干支 for cross interaction scoring.
            extended_gans = mingju_gans + [ganzhi[0]]
            extended_zhis = mingju_zhis + [ganzhi[1]]
            ly_score = score_yun(
                ly['ganzhi'], yongshen_primary, extended_gans, extended_zhis
            )

            # Plan 7.5b: liunian-level transmutation detection (with dedup against dayun)
            liunian_transmuted = None
            if chart_context:
                liunian_transmuted = _detect_xingyun_transmutation(
                    month_zhi=chart_context['month_zhi'],
                    base_mingju_zhis=mingju_zhis,
                    dayun_zhi=ganzhi[1],
                    liunian_zhi=ly['ganzhi'][1],
                    rizhu_gan=chart_context['rizhu_gan'],
                    force=chart_context['force'],
                    gan_he=chart_context['gan_he'],
                    original_geju_name=chart_context['original_geju_name'],
                    baseline_transmuted=dayun_transmuted,
                )

            ln_entries.append({
                'year': ly['year'],
                'ganzhi': ly['ganzhi'],
                'age': ly['age'],
                'label': ly_score['label'],
                'score': ly_score['score'],
                'note': ly_score['note'],
                'mechanisms': ly_score['mechanisms'],
                'transmuted': liunian_transmuted,    # NEW (Plan 7.5b)
            })
        out_liunian[str(idx)] = ln_entries

    return {
        'dayun': out_dayun,
        'liunian': out_liunian,
        'currentDayunIndex': current_idx,
        'yongshenSnapshot': yongshen_primary,
    }
