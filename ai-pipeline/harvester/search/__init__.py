"""Web search module for Navigator Harvester.

Provides pluggable search providers (DuckDuckGo, Yandex) and
source enrichment tools (URL fixer, source discoverer).
"""

from search.provider import SearchResult, WebSearchProvider

__all__ = ["SearchResult", "WebSearchProvider"]
