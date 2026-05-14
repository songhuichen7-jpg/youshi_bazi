"""Thin mapping layer: paipan结果 → card fields. Pure functions, no IO.

Paipan field names (confirmed by source inspection + runtime verification):
  - analyze_force()  → "sameRatio"   (float, same-side force ratio ∈ [0, 1])
  - identify_ge_ju() → "mainCandidate" dict with key "shishen" (十神 name,
    e.g. "食神") and "name" (格局 name, e.g. "食神格" — note trailing 格).
"""
from __future__ import annotations

from app.services.card.loader import TYPES, THRESHOLDS

_VALID_SHI_SHEN = {
    "比肩", "劫财", "食神", "伤官", "正财", "偏财",
    "正官", "七杀", "正印", "偏印",
}


def _classify_five_bucket(same_ratio: float) -> str:
    """Map same_ratio to one of 5 day-strength categories."""
    t = THRESHOLDS["thresholds"]
    if same_ratio >= t["strong_upper"]:
        return "极强"
    if same_ratio >= t["strong_lower"]:
        return "身强"
    if same_ratio >= t["neutral_lower"]:
        return "中和"
    if same_ratio >= t["weak_lower"]:
        return "身弱"
    return "极弱"


def classify_state(same_ratio: float) -> tuple[str, bool]:
    """Map 5-档 to 2-档 (绽放/蓄力) + borderline flag.

    Args:
        same_ratio: The "sameRatio" value from analyze_force(), in [0, 1].

    Returns:
        (state, borderline) where state is "绽放" or "蓄力" and borderline
        is True when same_ratio is within borderline_band of the strong_lower
        boundary (0.55 ± 0.05 by default).
    """
    category = _classify_five_bucket(same_ratio)
    state = THRESHOLDS["mapping"][category]
    boundary = THRESHOLDS["thresholds"]["strong_lower"]
    band = THRESHOLDS["borderline_band"]
    borderline = abs(same_ratio - boundary) < band
    return state, borderline


def lookup_type_id(day_stem: str, state: str) -> str:
    """Find type_id by (day_stem, state) in TYPES.

    Args:
        day_stem: The 日干 (e.g. "甲", "乙", ...).
        state:    "绽放" or "蓄力".

    Returns:
        Two-digit string type_id (e.g. "01").

    Raises:
        ValueError: When no matching type entry exists.
    """
    for tid, info in TYPES.items():
        if info["day_stem"] == day_stem and info["state"] == state:
            return tid
    raise ValueError(f"no type for day_stem={day_stem!r} state={state!r}")


def extract_ge_ju_shi_shen(ge_ju_result: dict) -> str:
    """Extract 十神 name from paipan's identify_ge_ju() result.

    Accepts the full identify_ge_ju() return dict. The actual 十神 name
    lives in ge_ju_result["mainCandidate"]["shishen"] (e.g. "食神").
    Falls back gracefully through several key strategies for robustness:

      1. mainCandidate["shishen"]  — primary path (paipan actual shape)
      2. mainCandidate["name"]     — format "食神格", strip trailing "格"
      3. Top-level "shiShen" / "shi_shen" / "shishen" / "name" / "十神"

    Returns "比肩" when no valid 十神 can be extracted (degenerate charts,
    格局不清, etc.) — "比肩" is always present in formations.json.
    """
    # Primary path: mainCandidate.shishen (paipan's actual field)
    main = ge_ju_result.get("mainCandidate")
    if isinstance(main, dict):
        # Direct shishen field
        val = main.get("shishen")
        if val and isinstance(val, str) and val in _VALID_SHI_SHEN:
            return val
        # name field like "食神格" — strip trailing 格
        val = main.get("name")
        if val and isinstance(val, str):
            stripped = val.rstrip("格")
            if stripped in _VALID_SHI_SHEN:
                return stripped

    # Fallback: top-level keys (for compatibility with alternate shapes / mocks)
    for key in ("shiShen", "shi_shen", "shishen", "name", "十神"):
        val = ge_ju_result.get(key)
        if val and isinstance(val, str):
            stripped = val.rstrip("格")
            if stripped in _VALID_SHI_SHEN:
                return stripped

    return "比肩"
