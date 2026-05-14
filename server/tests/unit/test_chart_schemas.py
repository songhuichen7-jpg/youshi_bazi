"""Pydantic schema validation for chart request/response."""
from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_birth_input_happy_path():
    from app.schemas.chart import BirthInput
    b = BirthInput(year=1990, month=5, day=12, hour=14, minute=30,
                   city="北京", gender="male")
    assert b.ziConvention == "early"
    assert b.useTrueSolarTime is True


def test_birth_input_hour_unknown_minus_one_ok():
    from app.schemas.chart import BirthInput
    b = BirthInput(year=1990, month=5, day=12, hour=-1, gender="female")
    assert b.hour == -1


def test_birth_input_hour_out_of_range_rejected():
    from app.schemas.chart import BirthInput
    with pytest.raises(ValidationError):
        BirthInput(year=1990, month=5, day=12, hour=24, gender="male")
    with pytest.raises(ValidationError):
        BirthInput(year=1990, month=5, day=12, hour=-2, gender="male")


def test_birth_input_gender_literal_enforced():
    from app.schemas.chart import BirthInput
    with pytest.raises(ValidationError):
        BirthInput(year=1990, month=5, day=12, hour=12, gender="X")


def test_birth_input_longitude_range():
    from app.schemas.chart import BirthInput
    with pytest.raises(ValidationError):
        BirthInput(year=1990, month=5, day=12, hour=12, gender="male", longitude=181)


def test_chart_create_request_label_length_40():
    from app.schemas.chart import ChartCreateRequest, BirthInput
    b = BirthInput(year=1990, month=5, day=12, hour=12, gender="male")
    # 40 char exactly
    ChartCreateRequest(birth_input=b, label="a" * 40)
    # 41 rejected
    with pytest.raises(ValidationError):
        ChartCreateRequest(birth_input=b, label="a" * 41)


def test_chart_create_request_label_optional():
    from app.schemas.chart import ChartCreateRequest, BirthInput
    b = BirthInput(year=1990, month=5, day=12, hour=12, gender="male")
    req = ChartCreateRequest(birth_input=b)
    assert req.label is None


def test_cache_slot_defaults():
    from app.schemas.chart import CacheSlot
    s = CacheSlot(kind="verdicts", key="", has_cache=False)
    assert s.regen_count == 0
    assert s.model_used is None
    assert s.generated_at is None


def test_config_response_shape():
    from app.schemas.config import ConfigResponse
    c = ConfigResponse(
        require_invite=True,
        engine_version="0.1.0",
        max_charts_per_user=15,
        guest_login_enabled=False,
    )
    assert c.require_invite is True
    assert c.max_charts_per_user == 15


def test_city_item_fields():
    from app.schemas.config import CityItem
    c = CityItem(name="北京", lng=116.4, lat=39.9)
    assert c.name == "北京"
