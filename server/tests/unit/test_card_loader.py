from __future__ import annotations

import pytest

from app.services.card.loader import (
    TYPES,
    FORMATIONS,
    SUBTAGS,
    THRESHOLDS,
    VERSION,
    load_all,
)


def test_types_loaded_with_20_entries():
    load_all()
    assert len(TYPES) == 20
    assert "01" in TYPES
    assert TYPES["01"]["cosmic_name"]  # non-empty


def test_formations_has_ten_shishen():
    load_all()
    assert len(FORMATIONS) == 10
    assert "食神" in FORMATIONS
    assert "suffixes" in FORMATIONS["食神"]
    assert set(FORMATIONS["食神"]["suffixes"].keys()) == {"绽放", "蓄力"}
    assert "绽放" in FORMATIONS["食神"]["golden_lines"]


def test_subtags_has_200_combos():
    load_all()
    total = sum(len(inner) for inner in SUBTAGS.values())
    assert total == 200
    for name, inner in SUBTAGS.items():
        for ss, tags in inner.items():
            assert len(tags) == 3


def test_card_display_copy_avoids_dangling_quotes():
    load_all()
    lines: list[str] = []
    for item in TYPES.values():
        lines.append(item.get("one_liner", ""))
    for item in FORMATIONS.values():
        lines.extend((item.get("golden_lines") or {}).values())
    for by_shishen in SUBTAGS.values():
        for tags in by_shishen.values():
            lines.extend(tags)

    for raw in lines:
        line = str(raw).strip()
        assert not line.startswith(('"', "“", "「", "『"))
        assert not line.endswith(('"', "”", "」", "』"))


def test_card_copy_keeps_pm_source_phrases_verbatim():
    load_all()

    assert FORMATIONS["七杀"]["golden_lines"]["蓄力"] == "压力大到失眠，但第二天闹钟响了还是干了"
    assert SUBTAGS["猫"]["七杀"][0] == "弓背是最后警告"


def test_thresholds_mapping_covers_five_categories():
    load_all()
    assert set(THRESHOLDS["mapping"].keys()) == {"极强", "身强", "中和", "身弱", "极弱"}


def test_version_loaded():
    load_all()
    assert VERSION.startswith("v")


def test_load_all_is_idempotent():
    load_all()
    first_types_ref = TYPES
    load_all()
    assert TYPES is first_types_ref  # same object, not reloaded
