from paipan.ge_ju import compute_ge_ju_and_guards, identify_ge_ju


def test_returns_ge_ju_string():
    paipan = {
        "year": {"gan": "癸", "zhi": "巳"},
        "month": {"gan": "甲", "zhi": "子"},
        "day":   {"gan": "丁", "zhi": "酉"},
        "hour":  {"gan": "甲", "zhi": "辰"},
    }
    force = {"比肩": 1.0, "劫财": 0.0, "食神": 0.5, "伤官": 0.0,
             "偏财": 0.0, "正财": 1.0, "七杀": 0.0, "正官": 2.0,
             "偏印": 1.5, "正印": 0.5}
    r = compute_ge_ju_and_guards(paipan, day_gan="丁", force=force)
    assert "geJu" in r
    assert "guards" in r
    assert isinstance(r["geJu"], str)
    assert isinstance(r["guards"], list)


def test_identify_siZhong_branch():
    # 四仲月 (子) — verified byte-identical to Node oracle
    r = identify_ge_ju({"yearGan": "癸", "monthGan": "甲", "monthZhi": "子",
                        "dayGan": "丁", "hourGan": "甲"})
    assert r["category"] == "四仲"
    assert r["monthZhi"] == "子"
    assert r["mainCandidate"]["name"] == "七杀格"


def test_identify_siKu_noTou_branch():
    # 四库月 (丑) 无透干 → 格局不清
    r = identify_ge_ju({"yearGan": "壬", "monthGan": "乙", "monthZhi": "丑",
                        "dayGan": "甲", "hourGan": "丁"})
    assert r["category"] == "四库"
    assert r["mainCandidate"]["name"] == "格局不清"


def test_identify_jianLu_branch():
    # 建禄月 (月令本气 = 日主比肩)
    r = identify_ge_ju({"yearGan": "丁", "monthGan": "甲", "monthZhi": "寅",
                        "dayGan": "甲", "hourGan": "癸"})
    assert r["mainCandidate"]["name"] == "建禄格"


def test_identify_siMeng_benqi_touGan_branch():
    # 四孟月 (寅) 本气透干
    r = identify_ge_ju({"yearGan": "庚", "monthGan": "甲", "monthZhi": "寅",
                        "dayGan": "乙", "hourGan": "丁"})
    assert r["category"] == "四孟"
    assert r["mainCandidate"] is not None
