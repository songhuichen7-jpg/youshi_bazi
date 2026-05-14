from paipan.zi_hour import convert_to_late_zi_convention, check_jieqi_boundary


def test_late_zi_2330_rolls_forward():
    r = convert_to_late_zi_convention(2024, 3, 15, 23, 30)
    assert r["converted"] is True
    assert r["year"] == 2024 and r["month"] == 3 and r["day"] == 16
    assert r["hour"] == 0 and r["minute"] == 30


def test_late_zi_before_23_no_change():
    r = convert_to_late_zi_convention(2024, 3, 15, 22, 30)
    assert r["converted"] is False
    assert r["day"] == 15 and r["hour"] == 22


def test_late_zi_month_boundary():
    r = convert_to_late_zi_convention(2024, 3, 31, 23, 30)
    assert r["converted"] is True
    assert r["month"] == 4 and r["day"] == 1


def test_jieqi_boundary_near():
    # 立春 2024-02-04 16:27:07 附近
    r = check_jieqi_boundary(2024, 2, 4, 16, 25)  # 前 ~2 分钟
    assert r["isNearBoundary"] is True
    assert "立春" in r["hint"] or "节气" in r["hint"]


def test_jieqi_boundary_far():
    r = check_jieqi_boundary(2024, 3, 15, 12, 0)  # 远离任何节气
    assert r["isNearBoundary"] is False
