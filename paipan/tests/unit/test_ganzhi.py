from paipan.ganzhi import GAN, ZHI, GAN_WUXING, ZHI_WUXING, GAN_YINYANG, split_ganzhi


def test_gan_count():
    assert len(GAN) == 10
    assert GAN[0] == "甲"
    assert GAN[-1] == "癸"


def test_zhi_count():
    assert len(ZHI) == 12
    assert ZHI[0] == "子"
    assert ZHI[-1] == "亥"


def test_wuxing_jia():
    assert GAN_WUXING["甲"] == "木"
    assert GAN_WUXING["丁"] == "火"
    assert GAN_WUXING["庚"] == "金"


def test_zhi_wuxing_yin():
    assert ZHI_WUXING["寅"] == "木"
    assert ZHI_WUXING["巳"] == "火"


def test_gan_yinyang():
    assert GAN_YINYANG["甲"] == "阳"
    assert GAN_YINYANG["乙"] == "阴"


def test_split_ganzhi():
    gan, zhi = split_ganzhi("癸巳")
    assert gan == "癸" and zhi == "巳"
