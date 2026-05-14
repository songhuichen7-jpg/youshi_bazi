"""Public helper: all_cities() — full flat list for server /api/cities route."""
from __future__ import annotations


def test_all_cities_returns_nonempty_sorted_list():
    from paipan.cities import all_cities
    items = all_cities()
    assert len(items) > 1000  # mainland dataset alone has >1k
    names = [t[0] for t in items]
    assert names == sorted(names), "must be name-sorted for stable ETag"


def test_all_cities_each_item_has_name_lng_lat():
    from paipan.cities import all_cities
    for name, lng, lat in all_cities()[:20]:
        assert isinstance(name, str) and name
        assert -180 <= lng <= 180
        assert -90 <= lat <= 90


def test_all_cities_includes_overseas_supplements():
    from paipan.cities import all_cities
    names = {t[0] for t in all_cities()}
    # NOTE: cities.py module-level _OVERSEAS 包含 "东京" "伦敦" 等
    assert "东京" in names
    assert "伦敦" in names


def test_all_cities_includes_mainland_samples():
    from paipan.cities import all_cities
    names = {t[0] for t in all_cities()}
    # cities-data.json 的 key 形态随数据集；接受"北京" 或 "北京市" 任一即可
    assert any(n in names for n in ("北京", "北京市"))


def test_all_cities_is_deterministic_across_calls():
    from paipan.cities import all_cities
    a = all_cities()
    b = all_cities()
    assert a == b


def test_all_cities_exported_from_package_root():
    import paipan
    assert callable(paipan.all_cities)
