import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "regression"))
from deep_diff import deep_diff


def test_equal_dicts_no_diff():
    assert deep_diff({"a": 1}, {"a": 1}) == []


def test_scalar_mismatch():
    diff = deep_diff({"a": 1}, {"a": 2})
    assert len(diff) == 1
    assert diff[0].path == "a"
    assert diff[0].actual == 1
    assert diff[0].expected == 2


def test_float_within_tolerance():
    assert deep_diff({"x": 1.0}, {"x": 1.0 + 1e-10}, float_tolerance=1e-9) == []


def test_float_outside_tolerance():
    diff = deep_diff({"x": 1.0}, {"x": 1.1}, float_tolerance=1e-9)
    assert len(diff) == 1


def test_nested_dict():
    diff = deep_diff({"a": {"b": 1}}, {"a": {"b": 2}})
    assert diff[0].path == "a.b"


def test_list_length_mismatch():
    diff = deep_diff([1, 2], [1, 2, 3])
    assert len(diff) >= 1
    assert "length" in diff[0].reason.lower()


def test_list_item_mismatch():
    diff = deep_diff([1, 2, 3], [1, 9, 3])
    assert any(d.path == "[1]" for d in diff)


def test_missing_key():
    diff = deep_diff({"a": 1}, {"a": 1, "b": 2})
    assert any(d.path == "b" and "missing" in d.reason.lower() for d in diff)


def test_extra_key():
    diff = deep_diff({"a": 1, "b": 2}, {"a": 1})
    assert any(d.path == "b" and "unexpected" in d.reason.lower() for d in diff)


def test_none_vs_value():
    diff = deep_diff({"a": None}, {"a": "value"})
    assert len(diff) == 1
