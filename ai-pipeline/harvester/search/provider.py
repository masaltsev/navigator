"""Abstract base for web search providers.

Each provider wraps a specific search engine (DuckDuckGo, Yandex, etc.)
behind a uniform async interface. Switching engines requires only changing
the provider instance — all enrichment logic stays the same.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class SearchResult:
    """Single search result returned by a provider."""

    title: str
    url: str
    snippet: str
    position: int
    source_engine: str = ""


@dataclass
class SearchStats:
    """Accumulated stats across multiple searches within a session."""

    total_queries: int = 0
    total_results: int = 0
    errors: int = 0
    _timings: list[float] = field(default_factory=list, repr=False)

    def record(self, num_results: int, elapsed: float, error: bool = False) -> None:
        self.total_queries += 1
        self.total_results += num_results
        self._timings.append(elapsed)
        if error:
            self.errors += 1

    @property
    def avg_time(self) -> float:
        return sum(self._timings) / len(self._timings) if self._timings else 0.0

    def summary(self) -> dict:
        return {
            "total_queries": self.total_queries,
            "total_results": self.total_results,
            "errors": self.errors,
            "avg_time_s": round(self.avg_time, 3),
        }


class WebSearchProvider(ABC):
    """Async interface for pluggable web search."""

    def __init__(self) -> None:
        self.stats = SearchStats()

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Human-readable engine name (e.g. 'duckduckgo', 'yandex')."""
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        region: str = "ru-ru",
        region_id: Optional[int] = None,
    ) -> list[SearchResult]:
        """Run a general web search and return ranked results.

        region_id: optional Yandex-style region id (lr) for geo bias; used by Yandex provider.
        """
        ...

    async def search_for_site(
        self,
        org_title: str,
        city: str = "",
        *,
        num_results: int = 10,
        region_id: Optional[int] = None,
    ) -> list[SearchResult]:
        """Search for an organisation's official website.

        Default implementation builds a query from title + city + 'официальный сайт'.
        region_id: optional (e.g. Yandex lr) for regional bias; pass when city/region is known.
        """
        parts = [f'"{org_title}"']
        if city:
            parts.append(city)
        parts.append("официальный сайт")
        query = " ".join(parts)
        return await self.search(query, num_results=num_results, region_id=region_id)

    async def search_by_domain_fragment(
        self,
        fragment: str,
        *,
        num_results: int = 5,
    ) -> list[SearchResult]:
        """Search for a website using a surviving domain fragment.

        Used when an org_website URL is broken/truncated but part of the
        domain is still recognisable (e.g. 'mikh-kcson ryazan').
        """
        query = f'"{fragment}" сайт'
        return await self.search(query, num_results=num_results)


def get_search_provider() -> WebSearchProvider:
    """Pick the best available search provider.

    Priority: DuckDuckGo (free, default) > Yandex Search API v2 (paid fallback).
    Set SEARCH_PROVIDER=yandex to force Yandex; it also requires
    YANDEX_SEARCH_FOLDER_ID and YANDEX_SEARCH_API_KEY env vars.
    """
    from config.settings import get_settings

    import structlog

    logger = structlog.get_logger("search.provider")
    settings = get_settings()

    force_yandex = settings.search_provider.lower() == "yandex"

    if force_yandex:
        folder_id = settings.yandex_search_folder_id
        api_key = settings.yandex_search_api_key
        if folder_id and api_key:
            from search.yandex_xml_provider import YandexSearchProvider

            provider = YandexSearchProvider()
            logger.info("search_provider_selected", provider="yandex")
            return provider
        logger.warning(
            "yandex_requested_but_not_configured",
            hint="Set YANDEX_SEARCH_FOLDER_ID and YANDEX_SEARCH_API_KEY; falling back to DuckDuckGo",
        )

    from search.duckduckgo_provider import DuckDuckGoProvider

    logger.info("search_provider_selected", provider="duckduckgo")
    return DuckDuckGoProvider()
