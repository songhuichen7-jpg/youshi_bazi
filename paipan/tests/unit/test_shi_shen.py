import pytest
from paipan.ganzhi import GAN
from paipan.shi_shen import get_shi_shen, SHI_SHEN_NAMES


def test_bijian_same_gan_yinyang():
    # 甲 对 甲 = 比肩
    assert get_shi_shen("甲", "甲") == "比肩"


def test_jiecai_same_wuxing_diff_yinyang():
    # 甲（阳木）对 乙（阴木）= 劫财
    assert get_shi_shen("甲", "乙") == "劫财"


def test_zhengyin_sheng_wo_diff_yinyang():
    # 甲（阳木）被 癸（阴水）生 = 正印
    assert get_shi_shen("甲", "癸") == "正印"


def test_pianyin_sheng_wo_same_yinyang():
    # 甲（阳木）被 壬（阳水）生 = 偏印
    assert get_shi_shen("甲", "壬") == "偏印"


@pytest.mark.parametrize("dayGan", GAN)
def test_all_dayGan_map_every_gan_to_some_shi_shen(dayGan):
    # 每种日干对每个天干都要返回一个合法的十神名
    for otherGan in GAN:
        r = get_shi_shen(dayGan, otherGan)
        assert r in SHI_SHEN_NAMES, f"{dayGan}→{otherGan} got {r!r}"
