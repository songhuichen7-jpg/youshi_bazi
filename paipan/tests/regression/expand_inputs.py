"""One-shot helper to expand the regression corpus from 50 → 300+ cases.

Reads the current birth_inputs.json, appends generated cases across the
categories called out in spec §8.4, dedupes by case_id (first-writer-wins),
and writes back.

Run:
    uv run --package paipan python paipan/tests/regression/expand_inputs.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
INPUTS_PATH = HERE / "birth_inputs.json"


# --- helpers ----------------------------------------------------------------

def _mk(case_id: str, **birth_input: Any) -> dict[str, Any]:
    # Normalise types: make sure ints are ints.
    return {"case_id": case_id, "birth_input": birth_input}


# --- Category generators ----------------------------------------------------

# 24 solar-term approximate dates (month, day, name) in the Gregorian calendar.
# Exact minute offsets vary by year, but dates are within ±1 day of these.
SOLAR_TERMS = [
    (2, 4, "lichun"),
    (2, 19, "yushui"),
    (3, 6, "jingzhe"),
    (3, 21, "chunfen"),
    (4, 5, "qingming"),
    (4, 20, "guyu"),
    (5, 6, "lixia"),
    (5, 21, "xiaoman"),
    (6, 6, "mangzhong"),
    (6, 21, "xiazhi"),
    (7, 7, "xiaoshu"),
    (7, 23, "dashu"),
    (8, 8, "liqiu"),
    (8, 23, "chushu"),
    (9, 8, "bailu"),
    (9, 23, "qiufen"),
    (10, 8, "hanlu"),
    (10, 23, "shuangjiang"),
    (11, 7, "lidong"),
    (11, 22, "xiaoxue"),
    (12, 7, "daxue"),
    (12, 22, "dongzhi"),
    (1, 6, "xiaohan"),
    (1, 20, "dahan"),
]


def gen_jieqi() -> list[dict[str, Any]]:
    """Solar-term boundary crossings: sample multiple years per term."""
    out: list[dict[str, Any]] = []
    # Years to sample — spread across modern era, avoiding DST window collision.
    years = [1995, 2000, 2010, 2018]
    cities = ["北京", "上海", "广州"]
    genders = ["male", "female"]
    idx = 0
    for (m, d, name) in SOLAR_TERMS:
        y = years[idx % len(years)]
        city = cities[idx % len(cities)]
        gender = genders[idx % 2]
        # Three samples around the expected boundary: before / at / after.
        out.append(_mk(
            f"jieqi-ex-{name}-{y}-before",
            year=y, month=m, day=d, hour=0, minute=30,
            city=city, gender=gender, useTrueSolarTime=False,
        ))
        out.append(_mk(
            f"jieqi-ex-{name}-{y}-noon",
            year=y, month=m, day=d, hour=12, minute=0,
            city=city, gender=gender, useTrueSolarTime=False,
        ))
        out.append(_mk(
            f"jieqi-ex-{name}-{y}-late",
            year=y, month=m, day=d, hour=23, minute=30,
            city=city, gender=gender, useTrueSolarTime=False,
        ))
        idx += 1
    return out


def gen_zi_cross_day() -> list[dict[str, Any]]:
    """子时跨日: hours 23:00–00:59 spanning day boundary, both conventions."""
    out: list[dict[str, Any]] = []
    # Use a spread of dates/years for variety.
    samples = [
        (2020, 1, 15), (2020, 6, 20), (2020, 12, 31),
        (2015, 5, 10), (2015, 10, 5),
        (2005, 3, 17), (2005, 11, 23),
        (1995, 7, 7), (1995, 8, 31),
        (1985, 2, 15), (1985, 9, 1),
        (1975, 4, 4), (1975, 6, 30),
        (2022, 2, 28), (2022, 10, 1),
        (2024, 2, 28), (2024, 12, 31),
    ]
    minutes = [0, 30, 59]
    hours = [23, 0]  # near midnight
    idx = 0
    for (y, m, d) in samples:
        for h in hours:
            for conv in ("early", "late"):
                minute = minutes[idx % len(minutes)]
                gender = "male" if idx % 2 == 0 else "female"
                out.append(_mk(
                    f"zi-ex-{y}-{m:02d}-{d:02d}-h{h:02d}m{minute:02d}-{conv}",
                    year=y, month=m, day=d, hour=h, minute=minute,
                    city="北京", gender=gender, ziConvention=conv,
                    useTrueSolarTime=False,
                ))
                idx += 1
    return out


def gen_dst() -> list[dict[str, Any]]:
    """China DST window 1986-05 .. 1991-09 — sample in and around it."""
    out: list[dict[str, Any]] = []
    # (year, month, day, hour, minute) tuples: in-DST and at boundaries.
    samples = [
        # 1986 (start 1986-05-04 02:00)
        (1986, 5, 4, 1, 30),
        (1986, 5, 4, 2, 0),
        (1986, 5, 4, 2, 30),
        (1986, 5, 4, 3, 30),
        (1986, 7, 15, 10, 0),
        (1986, 9, 14, 12, 0),  # end day
        # 1987
        (1987, 4, 12, 5, 0),
        (1987, 6, 1, 8, 0),
        (1987, 7, 20, 14, 0),
        (1987, 9, 13, 23, 59),
        # 1988
        (1988, 4, 10, 3, 0),
        (1988, 6, 15, 11, 0),
        (1988, 9, 11, 2, 30),
        # 1989
        (1989, 4, 16, 4, 15),
        (1989, 7, 4, 10, 0),
        (1989, 9, 17, 1, 0),
        # 1990
        (1990, 4, 15, 8, 0),
        (1990, 6, 21, 12, 0),
        (1990, 9, 16, 22, 30),
        # 1991
        (1991, 4, 14, 6, 0),
        (1991, 7, 7, 15, 45),
        (1991, 9, 15, 3, 30),  # last day
        # Outside-window sanity checks
        (1986, 1, 10, 8, 0),
        (1991, 11, 5, 9, 0),
        (1992, 7, 15, 12, 0),
    ]
    cities = ["北京", "上海", "广州", "成都"]
    for i, (y, m, d, h, mi) in enumerate(samples):
        gender = "male" if i % 2 == 0 else "female"
        city = cities[i % len(cities)]
        out.append(_mk(
            f"dst-ex-{y}-{m:02d}-{d:02d}-h{h:02d}m{mi:02d}-{city}",
            year=y, month=m, day=d, hour=h, minute=mi,
            city=city, gender=gender, useTrueSolarTime=True,
        ))
    return out


def gen_western() -> list[dict[str, Any]]:
    """Western-China city timezone boundary cases."""
    cities = ["乌鲁木齐", "喀什", "拉萨", "西宁", "兰州", "昆明", "成都", "重庆"]
    out: list[dict[str, Any]] = []
    # 2 samples per city = 16 cases.
    for i, city in enumerate(cities):
        y = 1988 + (i * 3) % 30
        out.append(_mk(
            f"tz-ex-{city}-{y}-morning",
            year=y, month=3 + (i % 8), day=10 + (i % 18), hour=7, minute=30,
            city=city, gender="male" if i % 2 == 0 else "female",
            useTrueSolarTime=True,
        ))
        out.append(_mk(
            f"tz-ex-{city}-{y + 5}-evening",
            year=y + 5, month=9 - (i % 4), day=5 + (i % 20), hour=20, minute=15,
            city=city, gender="female" if i % 2 == 0 else "male",
            useTrueSolarTime=True,
        ))
    return out


def gen_overseas() -> list[dict[str, Any]]:
    """Overseas: longitude only (no city)."""
    # (longitude, label) covering a range of longitudes.
    samples = [
        (-74.0, "newyork"),     # NYC
        (-122.4, "sanfrancisco"),
        (-0.1, "london"),
        (2.35, "paris"),
        (13.4, "berlin"),
        (55.3, "dubai"),
        (139.7, "tokyo"),
        (151.2, "sydney"),
        (100.5, "bangkok"),
        (103.8, "singapore"),
    ]
    out: list[dict[str, Any]] = []
    for i, (lng, label) in enumerate(samples):
        y = 1990 + (i * 2) % 30
        m = 1 + (i * 3) % 12
        d = 1 + (i * 7) % 28
        out.append(_mk(
            f"overseas-{label}-{y}",
            year=y, month=m, day=d, hour=10 + (i % 10), minute=15,
            longitude=lng, gender="male" if i % 2 == 0 else "female",
            useTrueSolarTime=True,
        ))
    return out


def gen_leap() -> list[dict[str, Any]]:
    """Lunar leap-month samples. Use Gregorian dates that land near the leap
    months in years 2012, 2014, 2017, 2020, 2023.
    """
    # Year-specific Gregorian date windows that land inside or near the leap
    # month. We sample multiple dates per year for coverage.
    year_windows = {
        2012: [(5, 10), (5, 22), (6, 5), (6, 18)],  # leap 四月
        2014: [(10, 15), (10, 28), (11, 5), (11, 18)],  # leap 九月
        2017: [(7, 5), (7, 18), (7, 25), (8, 10)],  # leap 六月
        2020: [(5, 10), (5, 22), (6, 5), (6, 18)],  # leap 四月
        2023: [(3, 25), (4, 10), (4, 25), (5, 5)],  # leap 二月
    }
    out: list[dict[str, Any]] = []
    i = 0
    for y, windows in year_windows.items():
        for (m, d) in windows:
            gender = "male" if i % 2 == 0 else "female"
            out.append(_mk(
                f"leap-ex-{y}-{m:02d}-{d:02d}",
                year=y, month=m, day=d, hour=12 + (i % 6), minute=0,
                city="北京", gender=gender, useTrueSolarTime=False,
            ))
            i += 1
    return out


def gen_wuxing() -> list[dict[str, Any]]:
    """Random-ish samples stressing element distribution / 格局 variety.

    Uses seed(42) for determinism.
    """
    random.seed(42)
    cities = ["北京", "上海", "广州", "成都", "西安", "杭州", "武汉", "南京"]
    out: list[dict[str, Any]] = []
    for i in range(40):
        y = random.randint(1960, 2020)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        h = random.randint(0, 23)
        mi = random.choice([0, 15, 30, 45])
        city = random.choice(cities)
        gender = random.choice(["male", "female"])
        out.append(_mk(
            f"wuxing-{i:03d}-{y}-{m:02d}-{d:02d}",
            year=y, month=m, day=d, hour=h, minute=mi,
            city=city, gender=gender, useTrueSolarTime=True,
        ))
    return out


def gen_geju() -> list[dict[str, Any]]:
    """Additional pattern (格局) samples. Independent deterministic seed."""
    random.seed(123)
    cities = ["北京", "天津", "济南", "沈阳", "重庆", "长沙", "福州", "厦门"]
    out: list[dict[str, Any]] = []
    for i in range(40):
        y = random.randint(1950, 2025)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        h = random.randint(0, 23)
        mi = random.choice([0, 10, 20, 30, 40, 50])
        city = random.choice(cities)
        gender = random.choice(["male", "female"])
        uts = random.choice([True, False])
        out.append(_mk(
            f"geju-{i:03d}-{y}-{m:02d}-{d:02d}",
            year=y, month=m, day=d, hour=h, minute=mi,
            city=city, gender=gender, useTrueSolarTime=uts,
        ))
    return out


def gen_dayun() -> list[dict[str, Any]]:
    """Extreme 大运: 4 years × 2 genders × 3 (m,d,h) = 24 cases."""
    out: list[dict[str, Any]] = []
    years = [1960, 1975, 1995, 2010]  # span yang/yin years
    date_hour_tuples = [(2, 4, 16), (8, 8, 8), (12, 22, 23)]
    genders = ["male", "female"]
    for y in years:
        for g in genders:
            for (m, d, h) in date_hour_tuples:
                out.append(_mk(
                    f"dayun-ex-{y}-{m:02d}-{d:02d}-h{h:02d}-{g}",
                    year=y, month=m, day=d, hour=h, minute=0,
                    city="北京", gender=g, useTrueSolarTime=False,
                ))
    return out


def gen_random() -> list[dict[str, Any]]:
    """Purely random samples for breadth. Seeded."""
    random.seed(7)
    cities = ["北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "南京",
              "西安", "长沙", "郑州", "昆明", "哈尔滨", "大连", "青岛"]
    out: list[dict[str, Any]] = []
    for i in range(20):
        y = random.randint(1920, 2030)
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        h = random.randint(0, 23)
        mi = random.randint(0, 59)
        city = random.choice(cities)
        gender = random.choice(["male", "female"])
        uts = random.choice([True, False])
        out.append(_mk(
            f"random-{i:03d}-{y}-{m:02d}-{d:02d}",
            year=y, month=m, day=d, hour=h, minute=mi,
            city=city, gender=gender, useTrueSolarTime=uts,
        ))
    return out


# --- Main -------------------------------------------------------------------

def main() -> None:
    existing: list[dict[str, Any]] = json.loads(INPUTS_PATH.read_text())
    seen = {c["case_id"] for c in existing}
    combined: list[dict[str, Any]] = list(existing)

    per_category = {
        "jieqi": gen_jieqi(),
        "zi": gen_zi_cross_day(),
        "dst": gen_dst(),
        "tz": gen_western(),
        "overseas": gen_overseas(),
        "leap": gen_leap(),
        "wuxing": gen_wuxing(),
        "geju": gen_geju(),
        "dayun": gen_dayun(),
        "random": gen_random(),
    }

    for cat, cases in per_category.items():
        added = 0
        for c in cases:
            if c["case_id"] in seen:
                continue
            seen.add(c["case_id"])
            combined.append(c)
            added += 1
        print(f"  {cat}: +{added} (generated {len(cases)})")

    INPUTS_PATH.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"\nTotal cases: {len(combined)}")


if __name__ == "__main__":
    main()
