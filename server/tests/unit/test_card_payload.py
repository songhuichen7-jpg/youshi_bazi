from __future__ import annotations

import pytest

from app.schemas.card import BirthInput
from app.services.card.loader import load_all
from app.services.card.payload import build_card_payload


@pytest.fixture(autouse=True)
def _load():
    load_all()


def test_build_card_returns_all_required_fields():
    b = BirthInput(year=1998, month=7, day=15, hour=14, minute=0)
    p = build_card_payload(b, nickname="小满")
    assert p.type_id in {f"{i:02d}" for i in range(1, 21)}
    assert p.cosmic_name
    assert p.day_stem in "甲乙丙丁戊己庚辛壬癸"
    assert p.state in ("绽放", "蓄力")
    assert p.state_icon in ("⚡", "🔋")
    assert len(p.subtags) == 3
    assert p.precision == "4-pillar"
    assert p.share_slug.startswith("c_")
    assert p.nickname == "小满"
    assert p.version


def test_build_card_with_unknown_hour_returns_3_pillar():
    b = BirthInput(year=1998, month=7, day=15, hour=-1, minute=0)
    p = build_card_payload(b, nickname=None)
    assert p.precision == "3-pillar"
    assert p.nickname is None


def test_build_card_state_icon_matches_state():
    b = BirthInput(year=1998, month=7, day=15, hour=14, minute=0)
    p = build_card_payload(b, nickname=None)
    if p.state == "绽放":
        assert p.state_icon == "⚡"
    else:
        assert p.state_icon == "🔋"


def test_build_card_subtag_matches_cosmic_name_and_shishen():
    from app.services.card.loader import SUBTAGS
    b = BirthInput(year=1998, month=7, day=15, hour=14, minute=0)
    p = build_card_payload(b, nickname=None)
    expected = SUBTAGS[p.cosmic_name][p.ge_ju]
    assert p.subtags == expected


def test_build_card_suffix_matches_formation_state():
    """Suffix must come from formations[ge_ju]['suffixes'][state] — state-aware."""
    from app.services.card.loader import FORMATIONS
    b = BirthInput(year=1998, month=7, day=15, hour=14, minute=0)
    p = build_card_payload(b, nickname=None)
    expected = FORMATIONS[p.ge_ju]["suffixes"][p.state]
    assert p.suffix == expected


def test_build_card_golden_line_matches_formation_state():
    from app.services.card.loader import FORMATIONS
    b = BirthInput(year=1998, month=7, day=15, hour=14, minute=0)
    p = build_card_payload(b, nickname=None)
    expected = FORMATIONS[p.ge_ju]["golden_lines"][p.state]
    assert p.golden_line == expected


def test_build_card_illustration_url_prefix():
    b = BirthInput(year=1998, month=7, day=15, hour=14, minute=0)
    p = build_card_payload(b, nickname=None)
    assert p.illustration_url.startswith("/static/cards/illustrations/")
    assert ".png?v=" in p.illustration_url


@pytest.mark.parametrize("year,month,day,hour", [
    (1990, 3, 20, 8),
    (1995, 11, 5, 22),
    (2000, 6, 1, 0),
    (1985, 9, 15, 12),
    (2005, 2, 28, 18),
])
def test_build_card_deterministic_across_runs(year, month, day, hour):
    b = BirthInput(year=year, month=month, day=day, hour=hour, minute=0)
    p1 = build_card_payload(b, nickname=None)
    p2 = build_card_payload(b, nickname=None)
    # Slug is random, but all content fields must match
    assert p1.type_id == p2.type_id
    assert p1.ge_ju == p2.ge_ju
    assert p1.subtags == p2.subtags
    assert p1.golden_line == p2.golden_line
    assert p1.suffix == p2.suffix
