"""Tests for search/provider.py — SearchResult, SearchStats, WebSearchProvider."""

import pytest
from search.provider import SearchResult, SearchStats, WebSearchProvider


class TestSearchResult:
    def test_frozen(self):
        r = SearchResult(title="T", url="https://x.ru", snippet="S", position=1)
        with pytest.raises(AttributeError):
            r.title = "new"  # type: ignore[misc]

    def test_fields(self):
        r = SearchResult(
            title="КЦСОН", url="https://kcson.ru", snippet="desc",
            position=2, source_engine="ddg",
        )
        assert r.title == "КЦСОН"
        assert r.url == "https://kcson.ru"
        assert r.position == 2
        assert r.source_engine == "ddg"

    def test_default_engine(self):
        r = SearchResult(title="", url="", snippet="", position=1)
        assert r.source_engine == ""


class TestSearchStats:
    def test_empty(self):
        s = SearchStats()
        assert s.total_queries == 0
        assert s.avg_time == 0.0

    def test_record(self):
        s = SearchStats()
        s.record(5, 1.2)
        s.record(3, 0.8)
        assert s.total_queries == 2
        assert s.total_results == 8
        assert s.errors == 0
        assert abs(s.avg_time - 1.0) < 0.01

    def test_record_error(self):
        s = SearchStats()
        s.record(0, 0.5, error=True)
        assert s.errors == 1

    def test_summary(self):
        s = SearchStats()
        s.record(3, 1.0)
        d = s.summary()
        assert d["total_queries"] == 1
        assert d["total_results"] == 3
        assert d["avg_time_s"] == 1.0


class TestWebSearchProviderABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            WebSearchProvider()  # type: ignore[abstract]
