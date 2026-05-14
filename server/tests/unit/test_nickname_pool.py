"""nickname_pool: 50-name pool + random + exclude."""
from app.services.nickname_pool import NICKNAMES, random_nickname


def test_pool_has_exactly_50_names():
    assert len(NICKNAMES) == 50


def test_pool_has_no_duplicates():
    assert len(set(NICKNAMES)) == 50


def test_random_nickname_returns_pool_member():
    for _ in range(20):
        assert random_nickname() in NICKNAMES


def test_random_nickname_with_exclude_skips_that_name():
    for _ in range(50):
        excluded = NICKNAMES[0]
        result = random_nickname(exclude=excluded)
        assert result != excluded


def test_random_nickname_exclude_none_works_like_default():
    for _ in range(10):
        assert random_nickname(exclude=None) in NICKNAMES


def test_pool_has_only_two_char_names():
    # Sanity: spec says 二字文学风
    for name in NICKNAMES:
        assert len(name) == 2, f"{name!r} is not 2 chars"
