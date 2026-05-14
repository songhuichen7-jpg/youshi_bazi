"""
Oracle-driven regression test.

For each fixture file, load the birth_input, run paipan.compute() with the
fixed ORACLE_NOW injected, and deep-diff against the Node engine's expected
output. ORACLE_NOW matches dump-oracle.js's mock so `todayYearGz` and friends
match byte-for-byte.
"""
from __future__ import annotations
import json
import pathlib
import sys
from datetime import datetime

import pytest

# Add regression directory to path so we can import deep_diff
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from deep_diff import deep_diff, format_diff

from paipan import compute

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
ORACLE_NOW = datetime(2026, 4, 17, 12, 0, 0)
ANALYZER_KEYS = {
    "force",
    "geJu",
    "ganHe",
    "zhiRelations",
    "notes",
    "dayStrength",
    "geju",
    "yongshen",
    "yongshenDetail",
    "xingyun",
}


def _load_fixtures() -> list[pathlib.Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


@pytest.mark.parametrize("fixture_path", _load_fixtures(), ids=lambda p: p.stem)
def test_regression(fixture_path: pathlib.Path) -> None:
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    case_id = data["case_id"]
    birth_input = dict(data["birth_input"])
    expected = data["expected"]

    actual = compute(**birth_input, _now=ORACLE_NOW)
    # Plan 7.1 adds analyzer fields on top of the legacy engine output. The
    # pre-existing regression oracle fixtures intentionally stay frozen to the
    # legacy subset; dedicated analyzer parity tests cover the new fields.
    actual = {k: v for k, v in actual.items() if k not in ANALYZER_KEYS}

    diffs = deep_diff(actual, expected, float_tolerance=1e-9)
    if diffs:
        pytest.fail(f"Regression diff for {case_id}:\n{format_diff(diffs)}")
