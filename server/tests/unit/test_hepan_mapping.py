# server/tests/unit/test_hepan_mapping.py
"""Tests for hepan.mapping — relationship classification + state-pair keys.

Covers all 6 categories + the 5 stem-合 + sample 相生/相克 + same-stem +
same-element-opposite-polarity. Also covers state_pair_key direction
collapse for 镜像 and direction translation for 滋养/火花."""
from __future__ import annotations

import pytest

from app.services.hepan.mapping import (
    classify,
    state_pair_icon_key,
    state_pair_key,
)


# ── classify(): 5 stem-合 (highest priority) ──────────────────────────

@pytest.mark.parametrize("a,b", [
    ("甲", "己"), ("乙", "庚"), ("丙", "辛"), ("丁", "壬"), ("戊", "癸"),
])
def test_classify_stem_he_returns_天作(a, b):
    cat, direction = classify(a, b)
    assert cat == "天作搭子"
    assert direction is None
    # Reverse direction also works
    cat2, _ = classify(b, a)
    assert cat2 == "天作搭子"


# ── classify(): same stem → 镜像 ──────────────────────────────────────

@pytest.mark.parametrize("stem", ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"])
def test_classify_same_stem_returns_镜像(stem):
    cat, direction = classify(stem, stem)
    assert cat == "镜像搭子"
    assert direction is None


# ── classify(): same element opposite polarity → 同频 ─────────────────

@pytest.mark.parametrize("a,b", [
    ("甲", "乙"), ("丙", "丁"), ("戊", "己"), ("庚", "辛"), ("壬", "癸"),
])
def test_classify_same_element_opposite_polarity_returns_同频(a, b):
    cat, direction = classify(a, b)
    assert cat == "同频搭子"
    assert direction is None


# ── classify(): 相生 → 滋养 (directional) ─────────────────────────────

def test_classify_wood_generates_fire():
    # 甲(木) → 丙(火): A 是 giver
    cat, direction = classify("甲", "丙")
    assert cat == "滋养搭子"
    assert direction == "giver"
    # 反之: 丙(火) ← 甲(木): A=丙 是 receiver
    cat, direction = classify("丙", "甲")
    assert cat == "滋养搭子"
    assert direction == "receiver"


def test_classify_water_generates_wood():
    cat, direction = classify("壬", "甲")  # 水→木
    assert cat == "滋养搭子"
    assert direction == "giver"


# ── classify(): 相克 → 火花 (directional, but only when not stem-合) ──

def test_classify_wood_controls_earth_attacker():
    # 甲(木) 克 戊(土) — but not 甲己合, so this should be 火花
    cat, direction = classify("甲", "戊")
    assert cat == "火花搭子"
    assert direction == "attacker"


def test_classify_stem_he_overrides_element_control():
    # 甲己 是合，即使 木克土 也判 天作
    cat, direction = classify("甲", "己")
    assert cat == "天作搭子"
    assert direction is None


def test_classify_metal_controls_wood_target():
    # 庚(金) 克 甲(木) — A=甲 是 target
    cat, direction = classify("甲", "庚")
    assert cat == "火花搭子"
    assert direction == "target"


# ── classify(): rejects unknown stems ─────────────────────────────────

def test_classify_rejects_unknown_stem():
    with pytest.raises(ValueError):
        classify("X", "甲")


# ── state_pair_key(): double burst / double charge are direction-free ─

@pytest.mark.parametrize("category,a_dir", [
    ("天作搭子", None), ("镜像搭子", None), ("同频搭子", None),
    ("滋养搭子", "giver"), ("滋养搭子", "receiver"),
    ("火花搭子", "attacker"), ("火花搭子", "target"),
])
def test_double_burst_yields_double_burst_key(category, a_dir):
    assert state_pair_key("绽放", "绽放", category, a_dir) == "double_burst"
    assert state_pair_key("蓄力", "蓄力", category, a_dir) == "double_charge"


# ── state_pair_key(): mixed cases ─────────────────────────────────────

def test_mixed_state_镜像_collapses_to_mixed_key():
    """同天干对称 → A绽B蓄 与 A蓄B绽 视为同一种 'mixed'。"""
    assert state_pair_key("绽放", "蓄力", "镜像搭子", None) == "mixed"
    assert state_pair_key("蓄力", "绽放", "镜像搭子", None) == "mixed"


def test_mixed_state_天作_uses_burst_charge_or_charge_burst():
    assert state_pair_key("绽放", "蓄力", "天作搭子", None) == "burst_charge"
    assert state_pair_key("蓄力", "绽放", "天作搭子", None) == "charge_burst"


def test_mixed_state_滋养_translates_to_giver_relative():
    # A=giver 绽放, B=receiver 蓄力 → giver_burst_receiver_charge
    key = state_pair_key("绽放", "蓄力", "滋养搭子", "giver")
    assert key == "giver_burst_receiver_charge"
    # A=receiver 绽放, B=giver 蓄力 → giver 仍在蓄力
    key = state_pair_key("绽放", "蓄力", "滋养搭子", "receiver")
    assert key == "giver_charge_receiver_burst"
    # A=giver 蓄力, B=receiver 绽放
    key = state_pair_key("蓄力", "绽放", "滋养搭子", "giver")
    assert key == "giver_charge_receiver_burst"


def test_mixed_state_火花_translates_to_attacker_relative():
    key = state_pair_key("绽放", "蓄力", "火花搭子", "attacker")
    assert key == "attacker_burst_target_charge"
    key = state_pair_key("绽放", "蓄力", "火花搭子", "target")
    assert key == "attacker_charge_target_burst"


def test_state_pair_key_rejects_invalid_state():
    with pytest.raises(ValueError):
        state_pair_key("?", "绽放", "天作搭子", None)


# ── state_pair_icon_key(): always A→B directional ─────────────────────

def test_state_pair_icon_key_directional():
    assert state_pair_icon_key("绽放", "绽放") == "double_burst"
    assert state_pair_icon_key("绽放", "蓄力") == "burst_charge"
    assert state_pair_icon_key("蓄力", "绽放") == "charge_burst"
    assert state_pair_icon_key("蓄力", "蓄力") == "double_charge"
