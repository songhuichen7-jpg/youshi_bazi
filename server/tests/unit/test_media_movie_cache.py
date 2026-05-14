import pytest

from app.api import media


def test_bundled_movie_poster_cache_is_broad_enough():
    assert sum(len(entries) for entries in media._MOVIE_POSTER_CACHE.values()) >= 5000

    for title in ("花样年华", "一一", "海上钢琴师", "重庆森林", "霸王别姬", "寄生虫"):
        assert media._lookup_movie_poster_cache(title) is not None


@pytest.mark.asyncio
async def test_movie_artwork_prefers_local_poster_cache(monkeypatch):
    cached = {
        "title": "花样年华",
        "poster_url": "https://image.tmdb.org/t/p/w500/test-poster.jpg",
        "year": "2000",
    }
    monkeypatch.setattr(media, "_MOVIE_POSTER_CACHE", {"花样年华": cached}, raising=False)

    async def fail_upstream(*args, **kwargs):
        raise AssertionError("movie poster cache should avoid upstream cover search")

    monkeypatch.setattr(media, "_tmdb_search_movie", fail_upstream)
    monkeypatch.setattr(media, "_itunes_search", fail_upstream)

    artwork = await media._resolve_artwork("movie", "花样年华", "王家卫")

    assert artwork == {
        "url": "https://image.tmdb.org/t/p/w500/test-poster.jpg",
        "year": "2000",
    }
