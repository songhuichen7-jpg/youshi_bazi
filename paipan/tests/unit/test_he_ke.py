"""Smoke tests for paipan.he_ke — downstream regression suite covers depth."""
from paipan.he_ke import (
    GAN_HE,
    SAN_HE_JU,
    ZHI_CHONG_PAIRS,
    find_gan_he,
    find_zhi_relations,
    is_chong,
    is_gan_he,
)


def test_gan_he_jia_ji_to_tu():
    # 甲己合化土
    assert GAN_HE["甲己"] == "土"
    assert GAN_HE["己甲"] == "土"
    assert is_gan_he("甲", "己") is True
    assert is_gan_he("己", "甲") is True
    assert is_gan_he("甲", "乙") is False


def test_find_gan_he_returns_pair_with_indices():
    # 年月日时天干含 甲(0) 己(2) → 合化土
    gans = ["甲", "丙", "己", "戊"]
    result = find_gan_he(gans)
    assert len(result) == 1
    he = result[0]
    assert he == {"a": "甲", "b": "己", "idx_a": 0, "idx_b": 2, "wuxing": "土"}


def test_zhi_chong_yin_shen():
    # 寅申冲
    assert is_chong("寅", "申") is True
    assert is_chong("申", "寅") is True
    assert is_chong("子", "丑") is False
    # pairs table shape
    assert ["寅", "申"] in ZHI_CHONG_PAIRS


def test_find_zhi_relations_shen_zi_chen_san_he():
    # 申子辰三合水局
    rel = find_zhi_relations(["申", "子", "辰", "午"])
    assert any(sh["wuxing"] == "水" and sh["type"] == "full" for sh in rel["sanHe"])
    # 子午冲 should also register
    assert any(c["a"] == "子" and c["b"] == "午" for c in rel["chong"])


def test_san_he_ju_shape():
    # All four 三合局 present with main = 中气支
    mains = {ju["main"] for ju in SAN_HE_JU}
    assert mains == {"子", "卯", "午", "酉"}
