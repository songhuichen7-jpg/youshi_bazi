from __future__ import annotations

from app.services.card.slug import birth_hash, generate_slug


def test_slug_format_c_prefix_plus_10_chars():
    slug = generate_slug()
    assert slug.startswith("c_")
    assert len(slug) == 12  # "c_" + 10


def test_slug_is_random_across_calls():
    slugs = {generate_slug() for _ in range(100)}
    assert len(slugs) == 100  # no collisions in small sample


def test_birth_hash_stable_for_same_input():
    h1 = birth_hash(year=1998, month=7, day=15, hour=14, minute=0)
    h2 = birth_hash(year=1998, month=7, day=15, hour=14, minute=0)
    assert h1 == h2


def test_birth_hash_differs_for_different_input():
    h1 = birth_hash(year=1998, month=7, day=15, hour=14, minute=0)
    h2 = birth_hash(year=1998, month=7, day=15, hour=15, minute=0)
    assert h1 != h2


def test_birth_hash_is_64_hex_chars():
    h = birth_hash(year=1998, month=7, day=15, hour=-1, minute=0)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
