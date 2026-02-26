"""DuckDuckGo search provider — free, no API key required.

Used as MVP provider for development and small-scale enrichment.
For production runs (>100 queries) switch to Yandex provider.

Rate-limiting: 2-second delay between queries to avoid blocks.
"""

import asyncio
import time
from typing import Optional

import structlog

from search.provider import SearchResult, WebSearchProvider

logger = structlog.get_logger(__name__)

_INTER_QUERY_DELAY = 2.0


class DuckDuckGoProvider(WebSearchProvider):
    """Web search via DuckDuckGo (duckduckgo-search package)."""

    def __init__(self, timeout: int = 15) -> None:
        super().__init__()
        self._timeout = timeout
        self._last_query_at: float = 0.0

    @property
    def engine_name(self) -> str:
        return "duckduckgo"

    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        region: str = "ru-ru",
        region_id: Optional[int] = None,
    ) -> list[SearchResult]:
        await self._rate_limit()

        t0 = time.monotonic()
        try:
            raw = await asyncio.to_thread(
                self._sync_search, query, num_results, region
            )
            results = [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                    position=i + 1,
                    source_engine="duckduckgo",
                )
                for i, r in enumerate(raw)
            ]
            elapsed = time.monotonic() - t0
            self.stats.record(len(results), elapsed)
            logger.info(
                "ddg_search",
                query=query[:80],
                results=len(results),
                elapsed=round(elapsed, 2),
            )
            return results
        except Exception as exc:
            elapsed = time.monotonic() - t0
            self.stats.record(0, elapsed, error=True)
            logger.warning("ddg_search_error", query=query[:80], error=str(exc))
            return []

    def _sync_search(
        self, query: str, max_results: int, region: str
    ) -> list[dict]:
        from duckduckgo_search import DDGS

        with DDGS(timeout=self._timeout) as ddgs:
            return ddgs.text(
                query,
                region=region,
                safesearch="moderate",
                max_results=max_results,
            )

    async def _rate_limit(self) -> None:
        """Enforce minimum delay between queries."""
        now = time.monotonic()
        elapsed = now - self._last_query_at
        if elapsed < _INTER_QUERY_DELAY and self._last_query_at > 0:
            await asyncio.sleep(_INTER_QUERY_DELAY - elapsed)
        self._last_query_at = time.monotonic()
