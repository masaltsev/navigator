"""
Site-specific markdown extractors — 0 LLM tokens.

Each extractor knows the DOM/markdown layout of a specific platform
(e.g. socinfo.ru, gov35.ru) and pulls structured fields directly
from crawled content using regex patterns on markdown.

This is more robust than CSS selectors for our pipeline because:
- Crawl4AI strips CSS classes/IDs from cleaned_html
- Our pipeline operates on markdown, not raw HTML
- Markdown output from the same CMS is 100 % consistent
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

import structlog

from strategies.site_extractors.socinfo import SocinfoExtractor

logger = structlog.get_logger(__name__)


_EXTRACTORS: dict[str, type] = {
    "socinfo": SocinfoExtractor,
}


class SiteExtractorRegistry:
    """Auto-detect site platform from URL and return the right extractor."""

    @staticmethod
    def detect_platform(url: str) -> Optional[str]:
        host = urlparse(url).hostname or ""
        if host.endswith(".socinfo.ru"):
            return "socinfo"
        return None

    @staticmethod
    def get_extractor(platform: str) -> Optional[object]:
        cls = _EXTRACTORS.get(platform)
        return cls() if cls else None

    @staticmethod
    def extract_if_known(url: str, markdown: str) -> Optional[dict]:
        """One-call convenience: detect platform → extract → return dict or None."""
        platform = SiteExtractorRegistry.detect_platform(url)
        if not platform:
            return None
        extractor = SiteExtractorRegistry.get_extractor(platform)
        if not extractor:
            return None
        result = extractor.extract(markdown, url)
        logger.info(
            "Site extractor '%s' extracted %d fields from %s",
            platform,
            sum(1 for v in result.values() if v),
            url,
        )
        return result
