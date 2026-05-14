# server/tests/unit/test_card_mapping.py
from __future__ import annotations

import pytest

from app.services.card.loader import load_all
from app.services.card.mapping import (
    classify_state,
    lookup_type_id,
    extract_ge_ju_shi_shen,
)


@pytest.fixture(autouse=True)
def _load():
    load_all()


def test_classify_state_strong_ratio_returns_绽放():
    state, borderline = classify_state(same_ratio=0.80)
    assert state == "绽放"
    assert borderline is False


def test_classify_state_weak_ratio_returns_蓄力():
    state, _ = classify_state(same_ratio=0.30)
    assert state == "蓄力"


def test_classify_state_中和_maps_to_绽放():
    state, _ = classify_state(same_ratio=0.40)  # 0.35-0.55 中和 → 绽放
    assert state == "绽放"


def test_classify_state_borderline_near_strong_lower():
    state, borderline = classify_state(same_ratio=0.56)  # within 0.05 of 0.55
    assert borderline is True


def test_classify_state_far_from_boundary_not_borderline():
    state, borderline = classify_state(same_ratio=0.80)
    assert borderline is False


def test_lookup_type_id_jia_绽放_returns_01():
    assert lookup_type_id(day_stem="甲", state="绽放") == "01"


def test_lookup_type_id_jia_蓄力_returns_02():
    assert lookup_type_id(day_stem="甲", state="蓄力") == "02"


def test_lookup_type_id_unknown_raises():
    with pytest.raises(ValueError):
        lookup_type_id(day_stem="X", state="绽放")


def test_extract_ge_ju_shi_shen_returns_valid_shi_shen():
    # Build a minimal mock ge_ju result that mirrors paipan's actual shape.
    # identify_ge_ju() returns a dict with "mainCandidate" containing "shishen"
    # (direct 十神 name like "食神") and "name" (格局 name like "食神格").
    # extract_ge_ju_shi_shen() receives the full identify_ge_ju() return value.
    mock = {
        "mainCandidate": {"name": "食神格", "shishen": "食神"},
        "candidates": [{"name": "食神格", "shishen": "食神"}],
    }
    assert extract_ge_ju_shi_shen(mock) == "食神"


def test_extract_ge_ju_falls_back_to_比肩_when_missing():
    assert extract_ge_ju_shi_shen({}) == "比肩"
