"""Shared chart fixture for prompt builder tests."""


def sample_chart() -> dict:
    """Representative paipan dict used by all prompt builder snapshot tests."""
    return {
        "sizhu": {"year": "庚午", "month": "辛巳", "day": "庚辰", "hour": "辛巳"},
        "rizhu": "庚",
        "shishen": {"year": "比肩", "month": "劫财", "day": "", "hour": "劫财"},
        "cangGan": {
            "year": [{"gan": "丁", "shiShen": "正官"}, {"gan": "己", "shiShen": "正印"}],
            "month": [{"gan": "丙", "shiShen": "七杀"}],
            "day": [{"gan": "戊", "shiShen": "偏印"}],
            "hour": [{"gan": "丙", "shiShen": "七杀"}],
        },
        "naYin": {"year": "路旁土", "month": "白蜡金", "day": "白蜡金", "hour": "白蜡金"},
        "dayun": [
            {"ganZhi": "壬午", "shiShen": "食神", "startAge": 6, "startYear": 1996, "years": []},
            {
                "ganZhi": "癸未", "shiShen": "伤官", "startAge": 16, "startYear": 2006,
                "years": [
                    {"year": 2006, "gz": "丙戌", "ss": "七杀"},
                    {"year": 2007, "gz": "丁亥", "ss": "正官"},
                    {"year": 2008, "gz": "戊子", "ss": "偏印"},
                    {"year": 2009, "gz": "己丑", "ss": "正印"},
                    {"year": 2010, "gz": "庚寅", "ss": "比肩"},
                ],
            },
            {"ganZhi": "甲申", "shiShen": "偏财", "startAge": 26, "startYear": 2016, "years": []},
            {"ganZhi": "乙酉", "shiShen": "正财", "startAge": 36, "startYear": 2026, "years": []},
        ],
        "lunar": {"year": 1990, "month": 5, "day": 12},
        "solarCorrected": {"year": 1990, "month": 5, "day": 12, "hour": 14, "minute": 30},
        "meta": {
            "input": {"year": 1990, "month": 5, "day": 12, "hour": 14, "minute": 30},
            "corrections": [],
        },
        "hourUnknown": False,
        "todayYearGz": "乙巳",
        "todayMonthGz": "庚辰",
        "todayDayGz": "甲子",
        "todayYmd": "2026-04-18",
    }
