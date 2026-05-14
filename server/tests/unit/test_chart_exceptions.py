"""Smoke tests for Plan 4 chart-related ServiceError subclasses."""
from __future__ import annotations

from app.services.exceptions import (
    ChartAlreadyDeleted,
    ChartLimitExceeded,
    ChartNotFound,
    InvalidBirthInput,
    ServiceError,
)


def test_invalid_birth_input_attrs():
    e = InvalidBirthInput()
    assert isinstance(e, ServiceError)
    assert e.code == "INVALID_BIRTH_INPUT"
    assert e.status == 400
    assert e.message == "出生信息无效"


def test_invalid_birth_input_accepts_custom_message():
    e = InvalidBirthInput("bad lunar date")
    assert e.message == "bad lunar date"
    assert e.code == "INVALID_BIRTH_INPUT"


def test_chart_not_found_attrs():
    e = ChartNotFound()
    assert isinstance(e, ServiceError)
    assert e.code == "CHART_NOT_FOUND"
    assert e.status == 404
    assert e.message == "命盘不存在"


def test_chart_limit_exceeded_carries_limit_in_details():
    e = ChartLimitExceeded(limit=15)
    assert isinstance(e, ServiceError)
    assert e.code == "CHART_LIMIT_EXCEEDED"
    assert e.status == 409
    assert e.details == {"limit": 15}
    assert "15" in e.message  # formatted into message


def test_chart_limit_exceeded_to_dict_shape():
    e = ChartLimitExceeded(limit=15)
    d = e.to_dict()
    assert d["code"] == "CHART_LIMIT_EXCEEDED"
    assert d["details"] == {"limit": 15}
    assert isinstance(d["message"], str)


def test_chart_already_deleted_attrs():
    e = ChartAlreadyDeleted()
    assert isinstance(e, ServiceError)
    assert e.code == "CHART_ALREADY_DELETED"
    assert e.status == 409
    assert e.message == "命盘已在软删状态"
