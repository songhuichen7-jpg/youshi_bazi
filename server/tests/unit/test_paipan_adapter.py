"""paipan_adapter: thin wrapper mapping Pydantic ↔ paipan.compute."""
from __future__ import annotations

import pytest


def test_resolve_city_hits_canonical():
    from app.services.paipan_adapter import resolve_city
    r = resolve_city("北京市")
    assert r is not None
    assert isinstance(r["canonical"], str) and r["canonical"]
    # canonical should be name-normalized form; precise form varies by dataset
    assert isinstance(r["lng"], float)
    assert isinstance(r["lat"], float)


def test_resolve_city_none_on_empty():
    from app.services.paipan_adapter import resolve_city
    assert resolve_city(None) is None
    assert resolve_city("") is None
    assert resolve_city("   ") is None


def test_resolve_city_none_on_unknown():
    from app.services.paipan_adapter import resolve_city
    assert resolve_city("ZZZZ不存在的城市XYZ") is None


def test_is_cache_stale_same_version_false():
    from app.services.paipan_adapter import is_cache_stale
    import paipan
    assert is_cache_stale(paipan.VERSION) is False


def test_is_cache_stale_different_version_true():
    from app.services.paipan_adapter import is_cache_stale
    assert is_cache_stale("0.0.0") is True
    assert is_cache_stale("") is True


def test_run_paipan_happy_path():
    from app.schemas.chart import BirthInput
    from app.services.paipan_adapter import run_paipan
    import paipan
    b = BirthInput(year=1990, month=5, day=12, hour=14, minute=30,
                   city="北京", gender="male")
    paipan_dict, warnings, version = run_paipan(b)
    assert version == paipan.VERSION
    # paipan.compute returns sizhu / rizhu / shishen / ... — just spot-check a few
    assert "sizhu" in paipan_dict
    assert "dayun" in paipan_dict
    assert isinstance(warnings, list)
    # warnings not embedded back into paipan_dict
    assert "warnings" not in paipan_dict


def test_run_paipan_hour_unknown():
    from app.schemas.chart import BirthInput
    from app.services.paipan_adapter import run_paipan
    b = BirthInput(year=1990, month=5, day=12, hour=-1, gender="female")
    paipan_dict, warnings, _ = run_paipan(b)
    assert paipan_dict["hourUnknown"] is True


def test_run_paipan_unknown_city_yields_warning():
    from app.schemas.chart import BirthInput
    from app.services.paipan_adapter import run_paipan
    b = BirthInput(year=1990, month=5, day=12, hour=12,
                   city="ZZZZ不存在的城市XYZ", gender="male")
    _, warnings, _ = run_paipan(b)
    assert any("未识别城市" in w for w in warnings)


def test_run_paipan_valueerror_maps_to_invalidbirthinput(monkeypatch):
    from app.schemas.chart import BirthInput
    from app.services import paipan_adapter
    from app.services.exceptions import InvalidBirthInput

    def _boom(**kwargs):
        raise ValueError("bad input")

    monkeypatch.setattr(paipan_adapter, "paipan_compute", _boom)

    b = BirthInput(year=1990, month=5, day=12, hour=12, gender="male")
    with pytest.raises(InvalidBirthInput) as exc:
        paipan_adapter.run_paipan(b)
    assert "bad input" in str(exc.value)
