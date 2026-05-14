import pytest
from paipan.ganzhi import ZHI
from paipan.cang_gan import get_cang_gan


def test_yin_cang_jia_bing_wu():
    # 寅 藏 甲（主）丙（中）戊（余）
    r = get_cang_gan("寅")
    assert r["main"] == "甲"
    assert r.get("middle") == "丙"
    assert r.get("residual") == "戊"


def test_zi_cang_gui():
    # 子 只藏癸
    r = get_cang_gan("子")
    assert r["main"] == "癸"
    assert r.get("middle") is None
    assert r.get("residual") is None


@pytest.mark.parametrize("zhi", ZHI)
def test_every_zhi_has_cang_gan(zhi):
    r = get_cang_gan(zhi)
    assert "main" in r
    assert r["main"] is not None and len(r["main"]) == 1  # 一个天干
