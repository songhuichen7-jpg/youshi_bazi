from paipan.dayun import compute_dayun


def test_dayun_structure():
    r = compute_dayun(year=1990, month=5, day=15, hour=10, minute=30, gender="male")
    assert "startSolar" in r
    assert "startAge" in r
    assert "startYearsDesc" in r
    assert "list" in r
    assert isinstance(r["list"], list)
    assert len(r["list"]) == 8  # Node 取 slice(1,9) == 8 条


def test_dayun_entry_shape():
    r = compute_dayun(year=1990, month=5, day=15, hour=10, minute=30, gender="male")
    entry = r["list"][0]
    assert "index" in entry
    assert "ganzhi" in entry and len(entry["ganzhi"]) == 2
    assert "startAge" in entry
    assert "startYear" in entry
    assert "endYear" in entry
    assert "liunian" in entry
    assert len(entry["liunian"]) == 10  # 每运 10 流年


def test_dayun_gender_matters():
    male = compute_dayun(year=1990, month=5, day=15, hour=10, minute=30, gender="male")
    female = compute_dayun(year=1990, month=5, day=15, hour=10, minute=30, gender="female")
    # 阳年男顺行 vs 女逆行，第一运 ganzhi 应不同
    assert male["list"][0]["ganzhi"] != female["list"][0]["ganzhi"]
