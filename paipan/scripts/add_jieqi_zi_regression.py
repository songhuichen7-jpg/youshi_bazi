"""Add jieqi-near-zi-hour edge cases to the regression corpus.

Jieqi (节气) at 23:xx / 00:xx is the most error-prone zone in bazi 排盘
because it stacks 4 boundaries:
  · 月柱 may cross at jieqi (absolute time)
  · 日柱 may cross at midnight (early-zi) or 23:00 (late-zi)
  · 年柱 may cross if jieqi is 立春
  · 时柱 always stays 子 in 23-01

We pin the CURRENT behavior with explicit fixtures so any future change to
late-zi or zi-hour handling is intentional (will fail oracle parity).

Run from repo root:
    uv run --package paipan python paipan/scripts/add_jieqi_zi_regression.py

Then regenerate Node oracle:
    cd archive/paipan-engine
    node scripts/dump-oracle.js \\
      ../../paipan/tests/regression/birth_inputs.json \\
      ../../paipan/tests/regression/fixtures/

Then verify:
    uv run --package paipan pytest paipan/tests/regression/ -q
"""
from __future__ import annotations

import json
from pathlib import Path

INPUTS_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests" / "regression" / "birth_inputs.json"
)


def _mk(case_id: str, **birth_input) -> dict:
    return {"case_id": case_id, "birth_input": birth_input}


# ── Picked from probe_jieqi_at_zi_hour.py Stage 1 scan ────────────────
# 故意挑了 4 类典型 case，每类配 early / late zi 双轨，捕获 4 个轴叠加：
#   · 立春跨年柱: 1984-02-04 23:18, 1980-02-05 00:09
#   · 普通节气在 23:xx (晚子派会越过 jieqi): 寒露 1982-10-08 23:02
#   · 普通节气在 00:xx (晚子派不再跨 jieqi): 惊蛰 1981-03-06 00:05
#   · 节气前夜 23:xx-23:59 (last-minute boundary): 大雪 2024-12-06 23:17
# 每个 case 三个偏移 (前 5min / 节气当时 / 后 5min) × 两派 = 6 个 case
NEW_CASES: list[dict] = []


def _add_case_set(label: str, year: int, mo: int, d: int, h: int, mi: int):
    """六个 case：(-5, 0, +5) min × (early, late) zi convention.

    h/mi 已经是该 case 的 jieqi 时间（或一个边界点）。
    """
    from datetime import datetime, timedelta
    base = datetime(year, mo, d, h, mi)
    for off_label, dt in [("before5", base - timedelta(minutes=5)),
                          ("on", base),
                          ("after5", base + timedelta(minutes=5))]:
        for zi in ("early", "late"):
            cid = f"jieqi-zi-{label}-{off_label}-{zi}"
            NEW_CASES.append(_mk(
                cid,
                year=dt.year, month=dt.month, day=dt.day,
                hour=dt.hour, minute=dt.minute,
                gender="male",
                ziConvention=zi,
                useTrueSolarTime=False,
            ))


# 立春 1984-02-04 23:18:44 — 同时跨 年柱 + 月柱，hour=23 触发 late-zi 滚动
_add_case_set("lichun-1984", 1984, 2, 4, 23, 18)

# 立春 1980-02-05 00:09:28 — hour=0 不触发 late-zi 滚动，但 jieqi 仍可能切月年
_add_case_set("lichun-1980", 1980, 2, 5, 0, 9)

# 寒露 1982-10-08 23:02:09 — hour=23 + jieqi 在 23:xx，late-zi 滚动会过 jieqi
_add_case_set("hanlu-1982", 1982, 10, 8, 23, 2)

# 惊蛰 1981-03-06 00:05:07 — hour=0 不触发滚动，但靠近 jieqi 月柱要切
_add_case_set("jingzhe-1981", 1981, 3, 6, 0, 5)

# 大雪 2024-12-06 23:17:03 — 近期 case，hour=23 + jieqi 23:xx
_add_case_set("daxue-2024", 2024, 12, 6, 23, 17)


def main():
    existing = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))
    existing_ids = {c["case_id"] for c in existing}
    added = 0
    for case in NEW_CASES:
        if case["case_id"] in existing_ids:
            continue
        existing.append(case)
        added += 1

    INPUTS_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"appended {added} jieqi-near-zi cases (skipped {len(NEW_CASES)-added} already present)")
    print(f"total cases now: {len(existing)}")
    print()
    print("Next step — regenerate Node oracle:")
    print("  cd archive/paipan-engine")
    print("  node scripts/dump-oracle.js \\")
    print("    ../../paipan/tests/regression/birth_inputs.json \\")
    print("    ../../paipan/tests/regression/fixtures/")


if __name__ == "__main__":
    main()
