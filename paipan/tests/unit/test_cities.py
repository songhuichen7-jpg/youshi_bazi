from paipan.cities import get_city_coords


def test_beijing():
    c = get_city_coords("北京")
    assert c is not None
    assert abs(c.lng - 116.4) < 0.5  # 宽松；精确值从 oracle diff 中锁定
    assert c.canonical == "北京"


def test_shanghai():
    c = get_city_coords("上海")
    assert c is not None
    assert c.canonical == "上海"


def test_shaoshan():
    c = get_city_coords("韶山")
    assert c is not None
    assert abs(c.lng - 112.53) < 0.5


def test_unknown_returns_none():
    assert get_city_coords("某小县城") is None


def test_empty_returns_none():
    assert get_city_coords("") is None
