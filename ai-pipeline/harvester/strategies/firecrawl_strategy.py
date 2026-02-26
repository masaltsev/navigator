"""
Firecrawl Cloud fallback for sites that Crawl4AI/Playwright cannot render.

Use cases:
  - SPA sites (React/Vue) that don't SSR content
  - Sites behind Cloudflare/DDoS-Guard that block headless browsers
  - Sites with CAPTCHA or aggressive bot detection

Firecrawl Cloud uses real browser infrastructure with rotation and
anti-detection, returning clean markdown.

Configuration:
  FIRECRAWL_API_KEY: API key for Firecrawl Cloud (firecrawl.dev)

The strategy is invoked as a fallback when Crawl4AI fails. It can also
be used directly via CLI --firecrawl flag.
"""

from dataclasses import dataclass
from typing import Optional

import httpx
import structlog

from config.settings import get_settings
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)

FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"


@dataclass
class FirecrawlResult:
    """Result from Firecrawl API scrape."""

    url: str
    markdown: str
    success: bool
    title: Optional[str] = None
    status_code: Optional[int] = None
    error: Optional[str] = None


class FirecrawlClient:
    """
    HTTP client for Firecrawl Cloud API.

    Scrapes a single URL and returns markdown content. Designed as a
    drop-in fallback when Crawl4AI/Playwright fails.
    """

    def __init__(
        self,
        api_key: str = "",
        timeout: float = 60.0,
    ):
        self._api_key = api_key or get_settings().firecrawl_api_key
        self._timeout = timeout
        self._enabled = bool(self._api_key)

        self._total_calls = 0
        self._successful = 0
        self._failed = 0

        if not self._enabled:
            logger.debug("firecrawl_disabled", reason="no API key")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=2, min=3, max=30),
        retry=retry_if_exception_type(
            (httpx.ConnectError, httpx.TimeoutException, httpx.ReadTimeout)
        ),
    )
    async def scrape(self, url: str) -> FirecrawlResult:
        """
        Scrape a single URL via Firecrawl Cloud API.

        Returns markdown content suitable for LLM processing.
        """
        if not self._enabled:
            return FirecrawlResult(
                url=url, markdown="", success=False,
                error="Firecrawl API key not configured",
            )

        self._total_calls += 1

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }

        payload = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "waitFor": 3000,
            "timeout": int(self._timeout * 1000),
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    FIRECRAWL_API_URL,
                    json=payload,
                    headers=headers,
                )

            if resp.status_code != 200:
                self._failed += 1
                error_msg = f"Firecrawl API error {resp.status_code}: {resp.text[:200]}"
                logger.warning(
                    "firecrawl_error",
                    url=url,
                    status_code=resp.status_code,
                    error=resp.text[:200],
                )
                return FirecrawlResult(
                    url=url, markdown="", success=False,
                    status_code=resp.status_code, error=error_msg,
                )

            body = resp.json()
            data = body.get("data", {})
            markdown = data.get("markdown", "")
            title = data.get("metadata", {}).get("title")

            if not markdown.strip():
                self._failed += 1
                return FirecrawlResult(
                    url=url, markdown="", success=False,
                    error="Empty markdown from Firecrawl",
                )

            self._successful += 1
            logger.info(
                "firecrawl_success",
                url=url,
                markdown_len=len(markdown),
                title=title,
            )

            return FirecrawlResult(
                url=url,
                markdown=markdown,
                success=True,
                title=title,
                status_code=resp.status_code,
            )

        except Exception as e:
            self._failed += 1
            logger.error("firecrawl_exception", url=url, error=str(e))
            return FirecrawlResult(
                url=url, markdown="", success=False,
                error=str(e),
            )

    async def scrape_multi_page(
        self, urls: list[tuple[str, str]],
    ) -> list[FirecrawlResult]:
        """
        Scrape multiple URLs sequentially (for multi-page fallback).

        Args:
            urls: list of (url, label) tuples
        """
        results = []
        for url, label in urls:
            result = await self.scrape(url)
            results.append(result)
        return results

    def get_metrics(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "successful": self._successful,
            "failed": self._failed,
            "success_rate": self._successful / max(self._total_calls, 1),
        }
