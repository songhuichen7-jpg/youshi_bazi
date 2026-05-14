# server/tests/unit/test_hepan_payload.py
"""Tests for hepan.payload composer — verifies a complete reading is
assembled correctly from card data + 04a pairs + 04b dynamics."""
from __future__ import annotations

from collections import Counter

import pytest

from app.services.card.loader import TYPES, load_all as load_card
from app.services.hepan.loader import find_pair, load_all as load_hepan
from app.services.hepan.payload import (
    build_completed_payload,
    build_pending_payload,
)


@pytest.fixture(autouse=True)
def _load():
    load_card()
    load_hepan()


def test_pending_payload_only_has_a_side():
    resp = build_pending_payload(
        slug="abc12345",
        a_type_id="01",
        a_state="绽放",
        a_day_stem="甲",
        a_nickname="小满",
    )
    assert resp.status == "pending"
    assert resp.a.cosmic_name == "春笋"
    assert resp.a.nickname == "小满"
    assert resp.b is None
    assert resp.label is None
    assert resp.modifier is None


def test_completed_天作_甲己合_double_burst():
    resp = build_completed_payload(
        slug="abc12345",
        a_type_id="01", a_state="绽放", a_day_stem="甲", a_nickname="A",
        b_type_id="11", b_state="绽放", b_day_stem="己", b_nickname="B",
    )
    assert resp.status == "completed"
    assert resp.category == "天作搭子"
    # 04a 甲己合: 撑腰搭子
    assert resp.label == "撑腰搭子"
    assert len(resp.subtags) == 3
    assert resp.cta
    # double_burst modifier from 04b
    assert resp.modifier
    assert "天然默契" in resp.modifier or "加速器" in resp.modifier
    # ⚡⚡
    assert resp.state_pair == "⚡⚡"
    assert resp.state_pair_label == "全力释放期"
    # Pair theme color exists and looks like hex
    assert resp.pair_theme_color and resp.pair_theme_color.startswith("#")
    # Both sides populated with role
    assert resp.a.role
    assert resp.b.role


def test_completed_镜像_甲甲_mixed_state():
    resp = build_completed_payload(
        slug="abc12346",
        a_type_id="01", a_state="绽放", a_day_stem="甲", a_nickname="A",
        b_type_id="02", b_state="蓄力", b_day_stem="甲", b_nickname="B",
    )
    assert resp.category == "镜像搭子"
    assert resp.label == "双扛搭子"
    # 镜像 mixed 修饰句
    assert resp.modifier
    assert "同款" in resp.modifier
    # ⚡🔋 (A=绽放, B=蓄力)
    assert resp.state_pair == "⚡🔋"


def test_completed_滋养_giver_at_a_burst_receiver_charge():
    # 甲(木 giver) 绽放, 丙(火 receiver) 蓄力
    resp = build_completed_payload(
        slug="abc12347",
        a_type_id="01", a_state="绽放", a_day_stem="甲", a_nickname=None,
        b_type_id="04", b_state="蓄力", b_day_stem="丙", b_nickname=None,
    )
    assert resp.category == "滋养搭子"
    # 04a 甲01反脆弱 × 丙03自燃: 底气搭子
    assert resp.label == "底气搭子"
    # 04b giver_burst_receiver_charge
    assert resp.modifier
    assert "天然的供需匹配" in resp.modifier or "供需" in resp.modifier


def test_completed_滋养_swaps_when_pair_authored_in_reverse():
    # spec authored direction: '壬甲' (water → wood). Try '甲壬' first
    # (receiver → giver) — should still find data and swap roles.
    resp_forward, swapped_forward = (
        find_pair("壬", "甲")[0], find_pair("壬", "甲")[1],
    )
    assert not swapped_forward
    resp_reverse, swapped_reverse = (
        find_pair("甲", "壬")[0], find_pair("甲", "壬")[1],
    )
    # Same data, just swapped flag
    assert resp_reverse is resp_forward
    assert swapped_reverse

    # Now compose: A=甲 receiver, B=壬 giver → roles should be swapped
    resp = build_completed_payload(
        slug="abc12348",
        a_type_id="01", a_state="绽放", a_day_stem="甲", a_nickname=None,
        b_type_id="19", b_state="绽放", b_day_stem="壬", b_nickname=None,
    )
    # spec 04a stored with stem_a=壬: a_role='给你找到水源', b_role='有水我长得更快'
    # When we ask with A=甲, the swap means a_role is now 04a's b_role
    assert "长得更快" in resp.a.role or "扛" in resp.a.role
    assert "水源" in resp.b.role or "给" in resp.b.role


def test_completed_火花_attacker_burst():
    # 甲(木) 克 戊(土) — A 是 attacker
    resp = build_completed_payload(
        slug="abc12349",
        a_type_id="01", a_state="绽放", a_day_stem="甲", a_nickname=None,
        b_type_id="09", b_state="蓄力", b_day_stem="戊", b_nickname=None,
    )
    assert resp.category == "火花搭子"
    assert resp.label == "松土搭子"
    # 04b attacker_burst_target_charge
    assert resp.modifier
    # state pair ⚡🔋
    assert resp.state_pair == "⚡🔋"


def test_completed_同频_甲乙_double_charge():
    resp = build_completed_payload(
        slug="abc12350",
        a_type_id="02", a_state="蓄力", a_day_stem="甲", a_nickname=None,
        b_type_id="04", b_state="蓄力", b_day_stem="乙", b_nickname=None,
    )
    assert resp.category == "同频搭子"
    assert resp.label == "林荫搭子"
    assert resp.state_pair == "🔋🔋"
    assert resp.state_pair_label == "同步充电中"


def test_pair_theme_color_blends_both_sides():
    # 甲 theme #2D6A4F (绿), 丙 theme #F5A623 (橙) → blended
    resp = build_completed_payload(
        slug="abc12351",
        a_type_id="01", a_state="绽放", a_day_stem="甲", a_nickname=None,
        b_type_id="05", b_state="绽放", b_day_stem="丙", b_nickname=None,
    )
    assert resp.pair_theme_color
    # The blended hex shouldn't equal either side's exact theme
    assert resp.pair_theme_color != resp.a.theme_color
    assert resp.pair_theme_color != resp.b.theme_color


def test_completed_payload_covers_all_210_type_pairs():
    """Every unordered pair among 20 personal cards should render a hepan card."""
    card_types = [TYPES[key] for key in sorted(TYPES)]
    categories: Counter[str] = Counter()
    state_pairs: Counter[str] = Counter()
    count = 0

    for index, a in enumerate(card_types):
        for b in card_types[index:]:
            resp = build_completed_payload(
                slug=f"pair-{a['id']}-{b['id']}",
                a_type_id=a["id"],
                a_state=a["state"],
                a_day_stem=a["day_stem"],
                a_nickname="A",
                b_type_id=b["id"],
                b_state=b["state"],
                b_day_stem=b["day_stem"],
                b_nickname="B",
            )
            assert resp.status == "completed"
            assert resp.a and resp.b
            assert resp.category
            assert resp.label
            assert len(resp.subtags or []) == 3
            assert resp.description
            assert resp.modifier
            assert resp.cta
            categories[resp.category] += 1
            state_pairs[resp.state_pair or ""] += 1
            count += 1

    assert count == 210
    assert categories == {
        "镜像搭子": 30,
        "同频搭子": 20,
        "滋养搭子": 80,
        "火花搭子": 60,
        "天作搭子": 20,
    }
    assert state_pairs == {
        "⚡⚡": 55,
        "⚡🔋": 55,
        "🔋⚡": 45,
        "🔋🔋": 55,
    }
