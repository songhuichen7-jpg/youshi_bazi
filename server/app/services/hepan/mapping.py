"""Stem-pair → relationship category, plus direction (giver/receiver,
attacker/target) used to pick the correct dynamic modifier in 04b.

Source of truth: PM/specs/04_合盘系统.md §三 命理规则 + §四 10×10 矩阵.

Six categories:
  - 天作搭子   stem-合 (highest priority, 5 pairs)
  - 镜像搭子   same stem (10 pairs)
  - 同频搭子   same element, opposite yin/yang (5 pairs)
  - 滋养搭子   element-生 (20 pairs, directional: giver/receiver)
  - 火花搭子   element-克 (15 pairs, directional: attacker/target)
  - 互补搭子   none of the above (does not appear in the 10-stem matrix
               but kept as a fallback bucket for forward compat).

All functions are pure; no IO.
"""
from __future__ import annotations

from typing import Literal, Optional

# Stem → element (五行)
STEM_ELEMENT: dict[str, str] = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# Stem → yin/yang (阴阳). 阳 = odd index, 阴 = even.
STEM_POLARITY: dict[str, str] = {
    "甲": "阳", "乙": "阴",
    "丙": "阳", "丁": "阴",
    "戊": "阳", "己": "阴",
    "庚": "阳", "辛": "阴",
    "壬": "阳", "癸": "阴",
}

# 五行相生: A → B (A 生 B)
GENERATION: dict[str, str] = {
    "木": "火",
    "火": "土",
    "土": "金",
    "金": "水",
    "水": "木",
}

# 五行相克: A → B (A 克 B)
CONTROL: dict[str, str] = {
    "木": "土",
    "土": "水",
    "水": "火",
    "火": "金",
    "金": "木",
}

# 天干合 (五对)
STEM_HE: dict[str, str] = {
    "甲": "己", "己": "甲",
    "乙": "庚", "庚": "乙",
    "丙": "辛", "辛": "丙",
    "丁": "壬", "壬": "丁",
    "戊": "癸", "癸": "戊",
}


Category = Literal[
    "天作搭子", "镜像搭子", "同频搭子", "滋养搭子", "火花搭子", "互补搭子"
]
Direction = Literal["giver", "receiver", "attacker", "target", None]


def classify(stem_a: str, stem_b: str) -> tuple[Category, Direction]:
    """Map (stem_a, stem_b) → (category, a_direction).

    a_direction tells you A 的角色 in directional categories:
      - 滋养搭子: a_direction == "giver" 表示 A 是 give 能量的一方 (木→火 中木方)
      - 火花搭子: a_direction == "attacker" 表示 A 是发起 克 的一方 (木→土 中木方)
      - 其他类别:  a_direction is None.

    Raises:
        ValueError when either stem is not in STEM_ELEMENT.
    """
    if stem_a not in STEM_ELEMENT or stem_b not in STEM_ELEMENT:
        raise ValueError(f"unknown stem(s): {stem_a!r}, {stem_b!r}")

    # 1. 天干合 has highest priority — overrides any element relationship
    if STEM_HE.get(stem_a) == stem_b:
        return "天作搭子", None

    elem_a = STEM_ELEMENT[stem_a]
    elem_b = STEM_ELEMENT[stem_b]

    # 2. 同天干 → 镜像
    if stem_a == stem_b:
        return "镜像搭子", None

    # 3. 同五行 异阴阳 → 同频
    if elem_a == elem_b and STEM_POLARITY[stem_a] != STEM_POLARITY[stem_b]:
        return "同频搭子", None

    # 4. 相生 → 滋养
    if GENERATION.get(elem_a) == elem_b:
        return "滋养搭子", "giver"
    if GENERATION.get(elem_b) == elem_a:
        return "滋养搭子", "receiver"

    # 5. 相克 → 火花
    if CONTROL.get(elem_a) == elem_b:
        return "火花搭子", "attacker"
    if CONTROL.get(elem_b) == elem_a:
        return "火花搭子", "target"

    # 6. 兜底: 在 10 干内不应到达此分支 (5 元素 × 同/生/克全覆盖)
    return "互补搭子", None


def state_pair_key(
    state_a: str,
    state_b: str,
    category: Category,
    a_direction: Direction,
) -> str:
    """Pick the key into dynamics.json modifiers[category] for given states.

    Each state is "绽放" or "蓄力". Output keys mirror dynamics.json:

      - 镜像搭子: {double_burst, mixed, double_charge}
        (因同天干对称，A绽B蓄 与 A蓄B绽 等价合并为 mixed)
      - 滋养搭子 directional:
        {double_burst, giver_burst_receiver_charge,
         giver_charge_receiver_burst, double_charge}
      - 火花搭子 directional:
        {double_burst, attacker_burst_target_charge,
         attacker_charge_target_burst, double_charge}
      - 其他: {double_burst, burst_charge, charge_burst, double_charge}

    Raises:
        ValueError when state_a/state_b are not 绽放/蓄力.
    """
    if state_a not in ("绽放", "蓄力") or state_b not in ("绽放", "蓄力"):
        raise ValueError(f"invalid states: {state_a!r}, {state_b!r}")

    a_burst = state_a == "绽放"
    b_burst = state_b == "绽放"

    if a_burst and b_burst:
        return "double_burst"
    if not a_burst and not b_burst:
        return "double_charge"

    # Mixed case
    if category == "镜像搭子":
        return "mixed"

    if category == "滋养搭子" and a_direction in ("giver", "receiver"):
        # Translate to giver-relative key
        giver_burst = (a_direction == "giver" and a_burst) or (a_direction == "receiver" and b_burst)
        return "giver_burst_receiver_charge" if giver_burst else "giver_charge_receiver_burst"

    if category == "火花搭子" and a_direction in ("attacker", "target"):
        attacker_burst = (a_direction == "attacker" and a_burst) or (a_direction == "target" and b_burst)
        return "attacker_burst_target_charge" if attacker_burst else "attacker_charge_target_burst"

    # Default: A 是绽放 B 是蓄力 → burst_charge; 反之 → charge_burst
    return "burst_charge" if a_burst else "charge_burst"


def state_pair_icon_key(state_a: str, state_b: str) -> str:
    """Pick the state-pair icon key (⚡⚡/⚡🔋/🔋⚡/🔋🔋).

    Distinct from state_pair_key — this is purely directional A-then-B.
    """
    a_burst = state_a == "绽放"
    b_burst = state_b == "绽放"
    if a_burst and b_burst:
        return "double_burst"
    if not a_burst and not b_burst:
        return "double_charge"
    return "burst_charge" if a_burst else "charge_burst"
