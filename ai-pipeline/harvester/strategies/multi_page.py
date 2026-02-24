"""
Multi-page crawl strategy for organization websites.

Crawls the main page + common subpages (/kontakty, /o-nas, /uslugi, etc.),
merges all markdown into a single text block for LLM classification.

This addresses Sprint 1.10 findings:
  - H1: addresses and emails often live on /kontakty subpages
  - H2: full official title often on /o-nas or /svedeniya

Usage:
    crawler = MultiPageCrawler()
    merged = await crawler.crawl_organization("https://kcson-vologda.gov35.ru")
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

logger = logging.getLogger(__name__)

SUBPAGE_PATTERNS: list[tuple[str, str]] = [
    ("/kontakty", "Контакты"),
    ("/contacts", "Контакты"),
    ("/o-nas", "О нас"),
    ("/about", "О нас"),
    ("/ob-uchrezhdenii", "Об учреждении"),
    ("/uslugi", "Услуги"),
    ("/services", "Услуги"),
    ("/svedeniya", "Сведения"),
    ("/svedeniya-ob-organizacii", "Сведения об организации"),
    ("/strukturnye-podrazdeleniya", "Структурные подразделения"),
    ("/struktura", "Структура"),
    ("/otdeleniya", "Отделения"),
    ("/specialists", "Специалисты"),
    ("/spetsialisty", "Специалисты"),
    ("/rekvizity", "Реквизиты"),
    ("/requisites", "Реквизиты"),
    ("/dokumenty", "Документы"),
]

DEFAULT_MAX_SUBPAGES = 5
DEFAULT_SUBPAGE_TIMEOUT = 15000
DEFAULT_CRAWL_DELAY = 1.0

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class PageResult:
    """Result of crawling a single page."""
    url: str
    label: str
    markdown: str
    success: bool
    error: Optional[str] = None


@dataclass
class MultiPageResult:
    """Merged result from crawling multiple pages of an organization site."""
    base_url: str
    pages: list[PageResult] = field(default_factory=list)
    merged_markdown: str = ""
    total_pages_attempted: int = 0
    total_pages_success: int = 0

    @property
    def success(self) -> bool:
        return self.total_pages_success > 0


class MultiPageCrawler:
    """
    Crawls an organization website's main page and relevant subpages,
    then merges all content into a single markdown text for LLM processing.

    Subpage discovery:
      1. Try known URL patterns (SUBPAGE_PATTERNS) via HEAD/GET
      2. Scan main page markdown for internal links matching patterns
      3. Crawl up to max_subpages additional pages

    Merge strategy: sections separated by headers with page labels,
    keeping main page content first.
    """

    def __init__(
        self,
        max_subpages: int = DEFAULT_MAX_SUBPAGES,
        subpage_timeout_ms: int = DEFAULT_SUBPAGE_TIMEOUT,
        crawl_delay: float = DEFAULT_CRAWL_DELAY,
        headless: bool = True,
    ):
        self.max_subpages = max_subpages
        self.subpage_timeout_ms = subpage_timeout_ms
        self.crawl_delay = crawl_delay
        self.headless = headless

    async def crawl_organization(self, base_url: str) -> MultiPageResult:
        """
        Crawl main page + discovered subpages, merge into single markdown.

        Returns MultiPageResult with merged_markdown suitable for LLM input.
        """
        result = MultiPageResult(base_url=base_url)

        browser_config = BrowserConfig(
            headless=self.headless,
            enable_stealth=True,
            user_agent=os.getenv("CRAWL4AI_USER_AGENT", _USER_AGENT),
        )

        main_config = CrawlerRunConfig(
            word_count_threshold=0,
            page_timeout=30000,
            wait_until="domcontentloaded",
            delay_before_return_html=2.0,
            magic=True,
            simulate_user=True,
            cache_mode=CacheMode.BYPASS,
        )

        subpage_config = CrawlerRunConfig(
            word_count_threshold=0,
            page_timeout=self.subpage_timeout_ms,
            wait_until="domcontentloaded",
            delay_before_return_html=1.0,
            magic=True,
            simulate_user=True,
            cache_mode=CacheMode.BYPASS,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            main_page = await self._crawl_page(
                crawler, base_url, "Главная страница", main_config,
            )
            result.pages.append(main_page)
            result.total_pages_attempted += 1

            if main_page.success:
                result.total_pages_success += 1
            else:
                logger.error("Main page crawl failed for %s: %s", base_url, main_page.error)
                result.merged_markdown = ""
                return result

            subpage_urls = self._discover_subpages(
                base_url, main_page.markdown,
            )
            logger.info(
                "Discovered %d candidate subpages for %s",
                len(subpage_urls), base_url,
            )

            for url, label in subpage_urls[: self.max_subpages]:
                if self.crawl_delay > 0:
                    await asyncio.sleep(self.crawl_delay)

                page = await self._crawl_page(crawler, url, label, subpage_config)
                result.pages.append(page)
                result.total_pages_attempted += 1

                if page.success:
                    result.total_pages_success += 1
                else:
                    logger.warning("Subpage crawl failed: %s (%s)", url, page.error)

        result.merged_markdown = self._merge_pages(result.pages)

        logger.info(
            "Multi-page crawl complete: %s — %d/%d pages ok, merged %d chars",
            base_url,
            result.total_pages_success,
            result.total_pages_attempted,
            len(result.merged_markdown),
        )

        return result

    async def _crawl_page(
        self,
        crawler: AsyncWebCrawler,
        url: str,
        label: str,
        config: CrawlerRunConfig,
    ) -> PageResult:
        """Crawl a single page, return PageResult."""
        try:
            res = await crawler.arun(url=url, config=config)
            if not res.success:
                return PageResult(
                    url=url, label=label, markdown="",
                    success=False, error=res.error_message or "Unknown error",
                )
            md = res.markdown or res.fit_markdown or ""
            if len(md.strip()) < 50:
                return PageResult(
                    url=url, label=label, markdown="",
                    success=False, error="Page content too short (<50 chars)",
                )
            return PageResult(url=url, label=label, markdown=md, success=True)
        except Exception as e:
            return PageResult(
                url=url, label=label, markdown="",
                success=False, error=str(e),
            )

    def _discover_subpages(
        self,
        base_url: str,
        main_markdown: str,
    ) -> list[tuple[str, str]]:
        """
        Discover subpages to crawl via:
          1. Known URL patterns (SUBPAGE_PATTERNS)
          2. Internal links found in main page markdown

        Returns deduplicated list of (url, label) tuples.
        """
        parsed = urlparse(base_url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"
        base_normalized = base_url.rstrip("/")

        candidates: dict[str, str] = {}

        for path, label in SUBPAGE_PATTERNS:
            candidate = urljoin(base_normalized + "/", path.lstrip("/"))
            norm = candidate.rstrip("/")
            if norm != base_normalized and norm not in candidates:
                candidates[norm] = label

        link_pattern = re.compile(
            r'\[([^\]]*)\]\((/[a-z0-9\-_/]+)\)',
            re.IGNORECASE,
        )
        for match in link_pattern.finditer(main_markdown):
            link_text = match.group(1).strip()
            href = match.group(2)
            full_url = urljoin(base_origin, href).rstrip("/")

            if full_url == base_normalized:
                continue
            if full_url in candidates:
                continue
            if not self._is_relevant_subpage(href, link_text):
                continue
            candidates[full_url] = link_text or href

        href_attr_pattern = re.compile(
            r'href=["\'](' + re.escape(base_origin) + r'/[a-z0-9\-_/]+)["\']',
            re.IGNORECASE,
        )
        for match in href_attr_pattern.finditer(main_markdown):
            full_url = match.group(1).rstrip("/")
            if full_url == base_normalized:
                continue
            if full_url in candidates:
                continue
            path = urlparse(full_url).path
            if self._is_relevant_subpage(path, ""):
                candidates[full_url] = path

        scored: list[tuple[str, str, int]] = []
        for url, label in candidates.items():
            score = self._priority_score(url, label)
            scored.append((url, label, score))

        scored.sort(key=lambda x: x[2], reverse=True)

        return [(url, label) for url, label, _ in scored]

    def _is_relevant_subpage(self, path: str, link_text: str) -> bool:
        """Check if a discovered link is likely relevant for organization data."""
        path_lower = path.lower()

        irrelevant = (
            "/news", "/novosti", "/press", "/media", "/photo", "/foto",
            "/video", "/gallery", "/galereya", "/vacancy", "/vakansii",
            "/tenders", "/zakupki", "/login", "/register", "/admin",
            "/sitemap", "/rss", "/feed", "/wp-", "/bitrix",
        )
        for prefix in irrelevant:
            if prefix in path_lower:
                return False

        relevant_keywords = (
            "kontakt", "contact", "o-nas", "about", "uslugi", "service",
            "svedeniya", "struktur", "otdelen", "rekvizit", "requisit",
            "spetsialist", "specialist", "filial", "podrazd",
            "inform", "obshchie", "general",
        )
        combined = (path_lower + " " + link_text.lower())
        return any(kw in combined for kw in relevant_keywords)

    def _priority_score(self, url: str, label: str) -> int:
        """Score subpages by relevance for organization data extraction."""
        path = urlparse(url).path.lower()
        combined = path + " " + label.lower()

        high_priority = ("kontakt", "contact", "rekvizit", "requisit")
        medium_priority = ("o-nas", "about", "svedeniya", "uslugi", "service")
        lower_priority = ("struktur", "otdelen", "spetsialist", "specialist", "filial")

        for kw in high_priority:
            if kw in combined:
                return 100

        for kw in medium_priority:
            if kw in combined:
                return 50

        for kw in lower_priority:
            if kw in combined:
                return 25

        return 10

    def _merge_pages(self, pages: list[PageResult]) -> str:
        """
        Merge successful pages into a single markdown text.

        Format: each page's content is wrapped in a section header.
        Main page comes first; subpages follow by crawl order.
        Content is trimmed to avoid exceeding LLM context limits.
        """
        max_per_page = 15000
        max_total = 30000

        sections: list[str] = []
        total_chars = 0

        for page in pages:
            if not page.success or not page.markdown.strip():
                continue

            content = page.markdown.strip()
            if len(content) > max_per_page:
                content = content[:max_per_page] + "\n\n[... содержимое страницы обрезано ...]"

            section = f"## === {page.label} ({page.url}) ===\n\n{content}"

            if total_chars + len(section) > max_total and sections:
                logger.info(
                    "Merged text limit reached (%d chars), skipping remaining pages",
                    total_chars,
                )
                break

            sections.append(section)
            total_chars += len(section)

        return "\n\n---\n\n".join(sections)
