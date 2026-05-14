"""Plan 7.4 — static lookup tables for 行运 scoring engine.

Tables:
- GAN_HE_TABLE      — 5 对天干合化 (甲己→土,乙庚→金 等)
- ZHI_LIUHE_TABLE   — 6 对地支六合 (子丑→土,寅亥→木 等)
- SCORE_THRESHOLDS  — 5-bin 分类阈值

Existing wuxing tables are imported from paipan.ganzhi (GAN_WUXING /
ZHI_WUXING / WUXING_SHENG / WUXING_KE) — do NOT duplicate.

Spec: docs/superpowers/specs/2026-04-20-xingyun-engine-design.md
"""
from __future__ import annotations

# 天干五合 (Plan 7.4 §4.1) — frozenset({a, b}) → 化出五行
GAN_HE_TABLE: dict[frozenset[str], str] = {
    frozenset({'甲', '己'}): '土',
    frozenset({'乙', '庚'}): '金',
    frozenset({'丙', '辛'}): '水',
    frozenset({'丁', '壬'}): '木',
    frozenset({'戊', '癸'}): '火',
}

# 地支六合 (Plan 7.4 §4.2)
ZHI_LIUHE_TABLE: dict[frozenset[str], str] = {
    frozenset({'子', '丑'}): '土',
    frozenset({'寅', '亥'}): '木',
    frozenset({'卯', '戌'}): '火',
    frozenset({'辰', '酉'}): '金',
    frozenset({'巳', '申'}): '水',
    frozenset({'午', '未'}): '土',  # 午未传统标"火土无气"，简化标土
}

# 5-bin 分类下限阈值 (Plan 7.4 §3.4)
# >= 4 大喜; 2-3 喜; -1 to 1 平; -3 to -2 忌; <= -4 大忌
SCORE_THRESHOLDS: dict[str, int] = {
    '大喜': 4,
    '喜':   2,
    '平':   0,
    '忌':  -2,
    '大忌': -4,
}

# Plan 7.6 §4.2 — 多元素用神 weighted average 权重 (递减)
# 单元素 → weights=[1.0]; 2 元素 → [0.625, 0.375]; 3 元素 → [0.5, 0.3, 0.2];
# 4+ 元素 → 第 4 及以后权重 0 (截断保护)
YONGSHEN_WEIGHTS: list[float] = [0.5, 0.3, 0.2]
