from datetime import datetime

from paipan import compute

FIXED_NOW = datetime(2026, 4, 17, 12, 0, 0)  # 匹配 dump-oracle.js 的 mock 时间


def test_compute_smoke():
    r = compute(
        year=1990, month=5, day=15, hour=10, minute=30,
        city="北京", gender="male", useTrueSolarTime=True, _now=FIXED_NOW,
    )
    assert "sizhu" in r
    assert len(r["sizhu"]["year"]) == 2
    assert r["hourUnknown"] is False
    assert len(r["dayun"]["list"]) == 8


def test_compute_hour_unknown():
    r = compute(
        year=1990, month=5, day=15, hour=-1, minute=0,
        city="上海", gender="female", useTrueSolarTime=True, _now=FIXED_NOW,
    )
    assert r["hourUnknown"] is True
    assert r["sizhu"]["hour"] is None
    assert len(r["dayun"]["list"]) == 8


def test_compute_mao_zedong():
    # 毛泽东 1893-12-26 辰时，族谱"癸巳 甲子 丁酉 甲辰"
    r = compute(
        year=1893, month=12, day=26, hour=8, minute=0,
        gender="male", useTrueSolarTime=False, _now=FIXED_NOW,
    )
    assert r["sizhu"]["year"] == "癸巳"
    assert r["sizhu"]["month"] == "甲子"
    assert r["sizhu"]["day"] == "丁酉"
    assert r["sizhu"]["hour"] == "甲辰"
