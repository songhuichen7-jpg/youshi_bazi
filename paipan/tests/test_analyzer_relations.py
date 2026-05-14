"""Plan 7.2: targeted analyzer relation regression coverage."""
from __future__ import annotations

from paipan import compute
from paipan.he_ke import analyze_relations


def test_analyze_relations_exposes_sanhe():
    relations = analyze_relations(["巳", "酉", "丑"])
    assert relations["sanHe"] == [{"zhi": ["巳", "酉", "丑"], "wuxing": "金", "type": "full"}]


def test_analyze_relations_exposes_banhe():
    relations = analyze_relations(["申", "子"])
    assert relations["banHe"] == [{"zhi": ["申", "子"], "wuxing": "水"}]


def test_analyze_relations_exposes_sanhui():
    relations = analyze_relations(["亥", "子", "丑"])
    assert relations["sanHui"] == [{"zhi": ["亥", "子", "丑"], "wuxing": "水", "dir": "北"}]


def test_compute_exposes_ganhe_top_level():
    out = compute(
        year=1976,
        month=11,
        day=30,
        hour=6,
        minute=15,
        gender="female",
        city="成都",
    )
    assert out["ganHe"]["withRiZhu"] == [
        {"a": "丙", "b": "辛", "idx_a": 0, "idx_b": 3, "wuxing": "水"},
        {"a": "丙", "b": "辛", "idx_a": 2, "idx_b": 3, "wuxing": "水"},
    ]
