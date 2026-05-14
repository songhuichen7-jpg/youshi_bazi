"""Plan 7.2: analyzer parity with JS reference.

Loads server/tests/data/golden_analyzer_v2.json (10 cases captured from the JS
archive/paipan-engine/src/ming/analyze.js). For each case, run paipan.compute()
and assert the output matches the JS output exactly (within rounding tolerance
for floats).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from paipan import compute


GOLDEN = Path(__file__).parent.parent.parent / "server/tests/data/golden_analyzer_v2.json"
# Plan 7.6 note: golden_analyzer_v2 remains the JS parity fixture except for
# H_sanhui.dayStrength, which is now Python-authoritative 5-bin output ('极弱')
# because li_liang's classifier intentionally supersedes the JS 3-bin value.
CASE_IDS = ["A", "B", "C", "D", "E", "F", "G_sanhe", "H_sanhui", "I_ganhe_rizhu", "J_cong"]


def _sorted_json(items):
    return sorted(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in items)


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text())


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_analyzer_parity(golden, case_id):
    case = golden[case_id]
    inp = case["input"]
    out = compute(
        year=inp["year"],
        month=inp["month"],
        day=inp["day"],
        hour=inp["hour"],
        minute=inp["minute"],
        gender=inp["gender"],
        city=inp["city"],
    )

    assert out["dayStrength"] == case["dayStrength"], f"{case_id}: dayStrength"
    assert abs(out["force"]["sameSideScore"] - case["sameSideScore"]) < 0.05, f"{case_id}: sameSideScore"
    assert abs(out["force"]["otherSideScore"] - case["otherSideScore"]) < 0.05, f"{case_id}: otherSideScore"
    assert abs(out["force"]["sameRatio"] - case["sameRatio"]) < 0.005, f"{case_id}: sameRatio"
    assert out["force"]["congCandidate"] == case["congCandidate"], f"{case_id}: congCandidate"

    expected_scores = case["scores"]
    actual_scores = out["force"]["scores"]
    for ss_name, expected_val in expected_scores.items():
        actual_val = actual_scores.get(ss_name, 0)
        assert abs(actual_val - expected_val) < 0.05, (
            f"{case_id}: scores[{ss_name}] {actual_val} vs {expected_val}"
        )

    assert out["geJu"]["mainCandidate"]["name"] == case["geju"], f"{case_id}: geju"
    assert out["geJu"]["decisionNote"] == case["gejuNote"], f"{case_id}: gejuNote"

    actual_lh = sorted((x["a"], x["b"]) for x in out["zhiRelations"]["liuHe"])
    expected_lh = sorted((x["a"], x["b"]) for x in case["zhiRelations"]["liuHe"])
    assert actual_lh == expected_lh, f"{case_id}: liuHe"

    actual_ch = sorted((x["a"], x["b"]) for x in out["zhiRelations"]["chong"])
    expected_ch = sorted((x["a"], x["b"]) for x in case["zhiRelations"]["chong"])
    assert actual_ch == expected_ch, f"{case_id}: chong"

    actual_san_he = _sorted_json(out["zhiRelations"]["sanHe"])
    expected_san_he = _sorted_json(case["zhiRelations"]["sanHe"])
    assert actual_san_he == expected_san_he, f"{case_id}: sanHe"

    actual_ban_he = _sorted_json(out["zhiRelations"]["banHe"])
    expected_ban_he = _sorted_json(case["zhiRelations"]["banHe"])
    assert actual_ban_he == expected_ban_he, f"{case_id}: banHe"

    actual_san_hui = _sorted_json(out["zhiRelations"]["sanHui"])
    expected_san_hui = _sorted_json(case["zhiRelations"]["sanHui"])
    assert actual_san_hui == expected_san_hui, f"{case_id}: sanHui"

    actual_notes = _sorted_json(out["notes"])
    expected_notes = _sorted_json(case["notes"])
    assert actual_notes == expected_notes, f"{case_id}: notes"

    actual_force_relations = {
        key: _sorted_json(value) for key, value in out["force"]["relations"].items()
    }
    expected_force_relations = {
        key: _sorted_json(value) for key, value in case["forceRelations"].items()
    }
    assert actual_force_relations == expected_force_relations, f"{case_id}: forceRelations"

    actual_gan_he_all = _sorted_json(out["ganHe"]["all"])
    expected_gan_he_all = _sorted_json(case["ganHe"]["all"])
    assert actual_gan_he_all == expected_gan_he_all, f"{case_id}: ganHe.all"

    actual_gan_he_rizhu = _sorted_json(out["ganHe"]["withRiZhu"])
    expected_gan_he_rizhu = _sorted_json(case["ganHe"]["withRiZhu"])
    assert actual_gan_he_rizhu == expected_gan_he_rizhu, f"{case_id}: ganHe.withRiZhu"
