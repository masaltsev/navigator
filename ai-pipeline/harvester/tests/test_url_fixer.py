"""Tests for search/url_fixer.py."""

import pytest
from unittest.mock import AsyncMock, patch

from search.provider import SearchResult, WebSearchProvider
from search.url_fixer import (
    FixCandidate,
    FixResult,
    extract_domain_fragment,
    fix_broken_url,
    _score_candidate,
    check_url_reachable,
)


class TestExtractDomainFragment:
    def test_truncated_tld(self):
        assert extract_domain_fragment("https://mikh-kcson.ryazan.") == "mikh-kcson ryazan"

    def test_no_scheme(self):
        assert extract_domain_fragment("kcson23.uszn032.ru") == "kcson23 uszn032"

    def test_full_url(self):
        assert extract_domain_fragment("https://fond-tut.ru") == "fond-tut"

    def test_with_www(self):
        frag = extract_domain_fragment("http://www.kcson-vologda.gov35.ru")
        assert "kcson-vologda" in frag
        assert "gov35" in frag

    def test_with_path(self):
        frag = extract_domain_fragment("https://kcson.example.ru/kontakty")
        assert "kcson" in frag
        assert "kontakty" not in frag

    def test_empty_url(self):
        assert extract_domain_fragment("") == ""

    def test_only_tld(self):
        frag = extract_domain_fragment("https://example.ru")
        assert "example" in frag

    def test_multiple_subdomains(self):
        frag = extract_domain_fragment("https://irkcson.aln.socinfo.ru")
        assert "irkcson" in frag
        assert "aln" in frag
        assert "socinfo" in frag

    def test_trailing_dot(self):
        frag = extract_domain_fragment("civil-society.donland.")
        assert "civil-society" in frag
        assert "donland" in frag


class TestScoreCandidate:
    def test_domain_match_high(self):
        r = SearchResult(title="КЦСОН", url="https://mikh-kcson.ryazan.ru", snippet="", position=1)
        score, _ = _score_candidate(r, "mikh-kcson ryazan", "")
        assert score >= 50

    def test_title_match(self):
        r = SearchResult(
            title="КЦСОН Таврического района",
            url="https://tavrich.ru",
            snippet="Центр социального обслуживания",
            position=1,
        )
        score, _ = _score_candidate(r, "tavrich", "КЦСОН Таврического района")
        assert score > 0

    def test_social_penalty(self):
        r = SearchResult(title="VK", url="https://vk.com/club123", snippet="", position=1)
        score1, _ = _score_candidate(r, "club123", "")
        r2 = SearchResult(title="Site", url="https://club123.ru", snippet="", position=1)
        score2, _ = _score_candidate(r2, "club123", "")
        assert score2 > score1

    def test_https_bonus(self):
        r1 = SearchResult(title="", url="https://kcson.ru", snippet="", position=5)
        r2 = SearchResult(title="", url="http://kcson.ru", snippet="", position=5)
        s1, _ = _score_candidate(r1, "kcson", "")
        s2, _ = _score_candidate(r2, "kcson", "")
        assert s1 > s2

    def test_top_position_bonus(self):
        r1 = SearchResult(title="", url="https://x.ru", snippet="", position=1)
        r2 = SearchResult(title="", url="https://x.ru", snippet="", position=10)
        s1, _ = _score_candidate(r1, "x", "")
        s2, _ = _score_candidate(r2, "x", "")
        assert s1 > s2


class _MockProvider(WebSearchProvider):
    """Minimal provider that returns pre-configured results."""

    def __init__(self, results: list[SearchResult]):
        super().__init__()
        self._results = results

    @property
    def engine_name(self):
        return "mock"

    async def search(self, query, *, num_results=10, region="ru-ru"):
        return self._results[:num_results]


class TestFixBrokenUrl:
    @pytest.mark.asyncio
    async def test_no_fragment(self):
        provider = _MockProvider([])
        result = await fix_broken_url("", provider, verify_reachable=False)
        assert not result.fixed
        assert result.fragment == ""

    @pytest.mark.asyncio
    async def test_finds_candidate(self):
        mock_results = [
            SearchResult(
                title="КЦСОН Рязани",
                url="https://mikh-kcson.ryazan.ru",
                snippet="Центр",
                position=1,
            ),
        ]
        provider = _MockProvider(mock_results)

        result = await fix_broken_url(
            "https://mikh-kcson.ryazan.",
            provider,
            verify_reachable=False,
        )
        assert result.fragment == "mikh-kcson ryazan"
        assert len(result.candidates) == 1
        assert result.best is not None
        assert "mikh-kcson" in result.best.url

    @pytest.mark.asyncio
    async def test_skips_invalid_urls(self):
        mock_results = [
            SearchResult(title="X", url="not-a-url", snippet="", position=1),
            SearchResult(title="Y", url="https://valid.ru", snippet="", position=2),
        ]
        provider = _MockProvider(mock_results)

        result = await fix_broken_url(
            "https://valid.",
            provider,
            verify_reachable=False,
        )
        assert all("not-a-url" != c.url for c in result.candidates)

    @pytest.mark.asyncio
    async def test_min_score_filter(self):
        mock_results = [
            SearchResult(title="", url="https://unrelated.ru", snippet="", position=10),
        ]
        provider = _MockProvider(mock_results)

        result = await fix_broken_url(
            "https://specific-org.",
            provider,
            verify_reachable=False,
            min_score=50.0,
        )
        assert result.best is None
