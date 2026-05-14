"""Sample day-strength distribution from random birth inputs (Plan 7.6 Task 0).

Used to determine empirical thresholds for 极弱 / 极强 bins.

Audit note:
- ``li_liang.py`` does not currently expose ``dayScore`` / ``day_score``.
- The actual continuous numeric metric surfaced in ``force`` today is
  ``sameRatio``.
"""
from __future__ import annotations

import random

from paipan import compute


N = 1000
SEED = 42
FIELD_NAME = "sameRatio"


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def main() -> None:
    scores: list[float] = []
    errors = 0
    random.seed(SEED)

    for _ in range(N):
        year = random.randint(1900, 2030)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        hour = random.randint(0, 23)
        minute = random.randint(0, 59)
        gender = random.choice(["male", "female"])
        city = "北京"

        try:
            result = compute(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                gender=gender,
                city=city,
            )
            force = result.get("force") or {}
            day_score = force.get(FIELD_NAME)
            if day_score is not None:
                scores.append(float(day_score))
        except Exception:
            errors += 1
            continue

    if not scores:
        raise SystemExit("No valid scores collected")

    scores.sort()
    n = len(scores)

    def pct(p: float) -> float:
        return scores[min(int(n * p), n - 1)]

    print(f"field: {FIELD_NAME}")
    print(f"N (attempted): {N}")
    print(f"N (valid): {n}")
    print(f"errors: {errors}")
    print(f"range: [{_fmt(scores[0])}, {_fmt(scores[-1])}]")
    print(f"p5 = {_fmt(pct(0.05))}")
    print(f"p10 = {_fmt(pct(0.10))}")
    print(f"p25 = {_fmt(pct(0.25))}")
    print(f"p50 (median) = {_fmt(pct(0.50))}")
    print(f"p75 = {_fmt(pct(0.75))}")
    print(f"p90 = {_fmt(pct(0.90))}")
    print(f"p95 = {_fmt(pct(0.95))}")
    print()
    print(f"Suggested BIN_JI_QIANG_THRESHOLD = {_fmt(pct(0.95))}")
    print(f"Suggested BIN_JI_RUO_THRESHOLD = {_fmt(pct(0.05))}")


if __name__ == "__main__":
    main()
