"""Tests for search/source_discoverer.py."""

import pytest
from search.provider import SearchResult
from search.source_discoverer import (
    DiscoveryResult,
    discover_sources,
    _is_aggregator,
    _score_official_site,
)
from tests.test_url_fixer import _MockProvider


class TestIsAggregator:
    def test_2gis(self):
        assert _is_aggregator("https://2gis.ru/vologda/firm/123")

    def test_zoon(self):
        assert _is_aggregator("https://zoon.ru/org/123")

    def test_rusprofile(self):
        assert _is_aggregator("https://www.rusprofile.ru/id/12345")

    def test_regular(self):
        assert not _is_aggregator("https://kcson.ru")

    def test_yandex_maps(self):
        assert _is_aggregator("https://yandex.ru/maps/org/kcson/123")


class TestScoreOfficialSite:
    def test_gov_ru_bonus(self):
        r = SearchResult(
            title="КЦСОН", url="https://kcson.gov.ru", snippet="",
            position=1,
        )
        score = _score_official_site(r, "КЦСОН Вологодской области")
        assert score >= 25

    def test_title_match(self):
        r = SearchResult(
            title="КЦСОН Таврического района Омской области",
            url="https://tavrichkcson.ru",
            snippet="Комплексный центр социального обслуживания",
            position=1,
        )
        score = _score_official_site(r, "КЦСОН Таврического района")
        assert score > 30

    def test_low_score_unrelated(self):
        r = SearchResult(
            title="Интернет-магазин обуви",
            url="https://shoes.ru",
            snippet="Купить обувь",
            position=8,
        )
        score = _score_official_site(r, "КЦСОН Вологды")
        assert score <= 15


class TestDiscoverSources:
    @pytest.mark.asyncio
    async def test_finds_official_and_social(self):
        mock_results = [
            SearchResult(
                title="КЦСОН Вологодской области",
                url="https://kcson-vologda.gov35.ru",
                snippet="Комплексный центр",
                position=1,
            ),
            SearchResult(
                title="КЦСОН ВК",
                url="https://vk.com/kcson_vologda",
                snippet="Группа ВКонтакте",
                position=2,
            ),
            SearchResult(
                title="2GIS",
                url="https://2gis.ru/vologda/firm/kcson",
                snippet="Карточка",
                position=3,
            ),
        ]
        provider = _MockProvider(mock_results)

        result = await discover_sources(
            "КЦСОН Вологодской области",
            provider,
            city="Вологда",
            verify_reachable=False,
        )
        assert result.found_anything
        assert len(result.official_sites) >= 1
        assert result.official_sites[0].kind == "org_website"
        assert len(result.social_pages) == 1
        assert result.social_pages[0].kind == "vk_group"
        assert result.skipped_aggregators == 1

    @pytest.mark.asyncio
    async def test_no_results(self):
        provider = _MockProvider([])
        result = await discover_sources(
            "Несуществующая Организация",
            provider,
            verify_reachable=False,
        )
        assert not result.found_anything
        assert result.search_results_count == 0

    @pytest.mark.asyncio
    async def test_only_social(self):
        mock_results = [
            SearchResult(
                title="OK group",
                url="https://ok.ru/group/12345",
                snippet="",
                position=1,
            ),
        ]
        provider = _MockProvider(mock_results)

        result = await discover_sources(
            "Фонд помощи",
            provider,
            verify_reachable=False,
        )
        assert result.found_anything
        assert len(result.official_sites) == 0
        assert len(result.social_pages) == 1

    @pytest.mark.asyncio
    async def test_best_official(self):
        mock_results = [
            SearchResult(
                title="Фонд Помощи",
                url="https://fond-pomoshi.ru",
                snippet="Благотворительный фонд помощи",
                position=1,
            ),
            SearchResult(
                title="Фонд",
                url="https://other.ru",
                snippet="Другой",
                position=2,
            ),
        ]
        provider = _MockProvider(mock_results)

        result = await discover_sources(
            "Фонд Помощи",
            provider,
            city="Москва",
            verify_reachable=False,
        )
        best = result.best_official
        assert best is not None
        assert "fond-pomoshi" in best.url
