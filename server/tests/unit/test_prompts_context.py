"""app.prompts.context: chart context compaction + timing helpers."""
from __future__ import annotations


def _sample_paipan():
    return {
        "sizhu": {"year":"庚午","month":"辛巳","day":"庚辰","hour":"辛巳"},
        "rizhu": "庚",
        "shishen": {"year":"比肩","month":"劫财","day":"","hour":"劫财"},
        "cangGan": {
            "year":[{"gan":"丁","shiShen":"正官"},{"gan":"己","shiShen":"正印"}],
            "month":[{"gan":"丙","shiShen":"七杀"}],
            "day":[{"gan":"戊","shiShen":"偏印"}],
            "hour":[{"gan":"丙","shiShen":"七杀"}],
        },
        "naYin": {"year":"路旁土","month":"白蜡金","day":"白蜡金","hour":"白蜡金"},
        "dayun": [{"ganZhi":"壬午","shiShen":"食神","startAge":6,"startYear":1996,"years":[]}
                  for _ in range(8)],
        "lunar": {"year":1990,"month":5,"day":12},
        "solarCorrected": {"year":1990,"month":5,"day":12,"hour":14,"minute":30},
        "meta": {"input":{"year":1990,"month":5,"day":12,"hour":14,"minute":30},
                 "corrections":[]},
        "hourUnknown": False,
        "todayYearGz":"乙巳","todayMonthGz":"庚辰","todayDayGz":"甲子","todayYmd":"2026-04-18",
    }


def test_compact_chart_context_returns_string():
    from app.prompts.context import compact_chart_context
    s = compact_chart_context(_sample_paipan())
    assert isinstance(s, str)
    assert "庚午" in s
    assert "庚" in s


def test_compact_chart_context_includes_today_and_timing():
    from app.prompts.context import compact_chart_context
    s = compact_chart_context(_sample_paipan())
    assert "2026-04-18" in s or "乙巳" in s


def test_compact_chart_context_includes_known_gender():
    from app.prompts.context import compact_chart_context
    p = {**_sample_paipan(), "gender": "female"}
    s = compact_chart_context(p)
    assert "性别  女命" in s


def test_compact_chart_context_includes_birth_and_corrected_time_details():
    from app.prompts.context import compact_chart_context
    p = {
        **_sample_paipan(),
        "birthInput": {
            "year": 1990,
            "month": 5,
            "day": 12,
            "hour": 14,
            "minute": 30,
            "city": "北京",
            "longitude": 116.407526,
            "gender": "female",
            "ziConvention": "early",
            "useTrueSolarTime": True,
        },
        "lunar": "一九九〇年四月十八",
        "solarCorrected": "1990-05-12 13:19",
        "meta": {
            "input": {"year": 1990, "month": 5, "day": 12, "hour": 14, "minute": 30},
            "corrections": [
                {"type": "china_dst", "from": "1990-5-12 14:30", "to": "1990-5-12 13:30"},
                {
                    "type": "true_solar_time",
                    "resolvedCity": "北京",
                    "longitude": 116.407526,
                    "from": "1990-5-12 13:30",
                    "to": "1990-5-12 13:19",
                },
            ],
        },
    }

    s = compact_chart_context(p)

    assert "出生资料" in s
    assert "公历:1990-05-12 14:30" in s
    assert "出生地:北京" in s
    assert "经度:116.407526" in s
    assert "真太阳时:开启" in s
    assert "子初换日:早子" in s
    assert "校正后:1990-05-12 13:19" in s
    assert "农历:一九九〇年四月十八" in s
    assert "夏令时:1990-5-12 14:30→1990-5-12 13:30" in s
    assert "真太阳时:北京/116.407526 1990-5-12 13:30→1990-5-12 13:19" in s


def test_resolve_today_year_from_paipan():
    from app.prompts.context import resolve_today_year
    p = _sample_paipan()
    assert resolve_today_year(p) == 2026
    p2 = dict(p); p2["todayYmd"] = ""
    year = resolve_today_year(p2)
    assert isinstance(year, int) and year >= 2024
