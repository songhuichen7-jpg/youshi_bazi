"""
Unit tests for solar_time. Values are cross-checked against Node output
via oracle dump. We use a few known examples here; full regression covers rest.
"""
from paipan.solar_time import to_true_solar_time


def test_beijing_noon_no_shift():
    # 北京 (~116.4°E), 接近标准时区 120°E，偏移约 -14 分钟
    r = to_true_solar_time(2020, 6, 15, 12, 0, 116.4)
    assert r["year"] == 2020 and r["month"] == 6 and r["day"] == 15
    assert abs(r["shiftMinutes"]) < 30


def test_urumqi_large_shift():
    # 乌鲁木齐 ~87.6°E，偏移 -120 分钟以上
    r = to_true_solar_time(2020, 6, 15, 12, 0, 87.6)
    assert r["shiftMinutes"] < -100
    # 日期/时分应相应回滚
    assert r["hour"] <= 10  # 大致 10 点


def test_shaoshan_mao_zedong():
    # 112.53°E, 清晨 8:00
    r = to_true_solar_time(1893, 12, 26, 8, 0, 112.53)
    # 偏移是负的（早于北京时）
    assert r["shiftMinutes"] < 0
