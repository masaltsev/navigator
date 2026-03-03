"""
Event discovery strategy for organization websites.

Discovers event/news pages that were filtered out by the organization
multi_page crawler, crawls them, and extracts individual event entries
for classification via EventProcessor.

Architecture: Variant C (cached-hybrid) — during org crawl, /news and
/afisha pages are discovered but excluded from org-merge. This module
crawls those pages separately and splits them into individual events.

Usage:
    discoverer = EventDiscoverer()
    events = await discoverer.discover_events("https://example.com")
    # events = list of EventCandidate with raw markdown per event
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin, urlparse

import structlog

logger = structlog.get_logger(__name__)

EVENT_PAGE_PATTERNS: list[tuple[str, str]] = [
    ("/news", "Новости"),
    ("/novosti", "Новости"),
    ("/afisha", "Афиша"),
    ("/events", "Мероприятия"),
    ("/meropriyatiya", "Мероприятия"),
    ("/announcements", "Анонсы"),
    ("/anonsy", "Анонсы"),
    ("/press", "Пресс-центр"),
    ("/sobytiya", "События"),
]

EVENT_KEYWORDS = frozenset({
    "масленица", "мастер-класс", "мастеркласс", "концерт", "школа ухода",
    "фестиваль", "акция", "вебинар", "лекция", "семинар", "тренинг",
    "выставка", "экскурсия", "занятие", "кружок", "конкурс",
    "приглашаем", "состоится", "приглашает", "день открытых дверей",
    "активное долголетие", "серебряный возраст", "для пенсионеров",
    "55+", "60+", "старшего поколения", "клуб общения",
    "праздник", "встреча", "викторина", "спартакиада",
})

IRRELEVANT_MARKERS = frozenset({
    "тендер", "закупк", "вакансия", "вакансий", "прием на работу",
    "итоги аукциона", "протокол", "план-график",
})

_LINK_RE = re.compile(
    r'\[([^\]]{3,150})\]\((/[a-z0-9\-_/]+(?:\d{4})?[a-z0-9\-_/]*)\)',
    re.IGNORECASE,
)

_DATE_RE = re.compile(
    r'(\d{1,2})[.\s]*(января|февраля|марта|апреля|мая|июня|июля|августа|'
    r'сентября|октября|ноября|декабря|\d{1,2})[.\s]*(\d{4})?',
    re.IGNORECASE,
)

_MONTH_MAP = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


@dataclass
class EventCandidate:
    """A discovered event page/entry ready for EventProcessor."""
    url: str
    title: str
    markdown: str
    discovered_from: str
    freshness_days: Optional[int] = None


@dataclass
class EventDiscoveryResult:
    """Result of event discovery for an organization site."""
    base_url: str
    event_pages_found: int = 0
    candidates: list[EventCandidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class EventDiscoverer:
    """
    Discovers event pages on organization websites and splits them
    into individual event candidates for LLM classification.

    Two-phase approach:
      1. Crawl /news, /afisha, /events pages (first page only)
      2. Parse the news feed markdown into individual event entries
         using heading/date/link-based splitting
    """

    def __init__(
        self,
        max_event_pages: int = 3,
        max_events_per_page: int = 10,
        freshness_days: int = 60,
    ):
        self.max_event_pages = max_event_pages
        self.max_events_per_page = max_events_per_page
        self.freshness_days = freshness_days

    async def discover_events(
        self,
        base_url: str,
        main_page_markdown: Optional[str] = None,
    ) -> EventDiscoveryResult:
        """
        Discover and crawl event pages, extract event candidates.

        Args:
            base_url: Organization's base URL
            main_page_markdown: If available (from org crawl), used to discover
                               event page links without extra crawl.
        """
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

        from config.settings import get_settings

        result = EventDiscoveryResult(base_url=base_url)

        event_page_urls = self._find_event_pages(base_url, main_page_markdown)
        if not event_page_urls:
            logger.info("no_event_pages_found", url=base_url)
            return result

        result.event_pages_found = len(event_page_urls)
        logger.info(
            "event_pages_discovered",
            url=base_url,
            count=len(event_page_urls),
            pages=[url for url, _ in event_page_urls[:self.max_event_pages]],
        )

        browser_config = BrowserConfig(
            headless=True,
            enable_stealth=True,
            user_agent=get_settings().crawl4ai_user_agent,
            user_data_dir=get_settings().get_crawl4ai_browser_data_dir(),
        )
        crawl_config = CrawlerRunConfig(
            word_count_threshold=0,
            page_timeout=20000,
            wait_until="domcontentloaded",
            delay_before_return_html=2.0,
            magic=True,
            simulate_user=True,
            cache_mode=CacheMode.BYPASS,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            for page_url, page_label in event_page_urls[:self.max_event_pages]:
                try:
                    res = await crawler.arun(url=page_url, config=crawl_config)
                    if not res.success or not (res.markdown or "").strip():
                        result.errors.append(f"Failed to crawl {page_url}")
                        continue

                    markdown = res.markdown or res.fit_markdown or ""
                    candidates = self._split_into_events(
                        markdown, page_url, page_label,
                    )
                    result.candidates.extend(candidates)

                    logger.info(
                        "event_page_processed",
                        page_url=page_url,
                        candidates_found=len(candidates),
                    )
                except Exception as e:
                    result.errors.append(f"Error crawling {page_url}: {e}")
                    logger.warning(
                        "event_page_error",
                        page_url=page_url,
                        error=str(e),
                    )

        logger.info(
            "event_discovery_complete",
            url=base_url,
            total_candidates=len(result.candidates),
            pages_crawled=result.event_pages_found,
        )
        return result

    def discover_from_cached_markdown(
        self,
        base_url: str,
        event_page_markdowns: dict[str, str],
    ) -> EventDiscoveryResult:
        """
        Extract events from already-crawled event page markdowns (variant C).

        Args:
            base_url: Organization's base URL
            event_page_markdowns: {page_url: markdown} for /news, /afisha pages
        """
        result = EventDiscoveryResult(base_url=base_url)
        result.event_pages_found = len(event_page_markdowns)

        for page_url, markdown in event_page_markdowns.items():
            label = self._label_for_url(page_url)
            candidates = self._split_into_events(markdown, page_url, label)
            result.candidates.extend(candidates)

        return result

    def _find_event_pages(
        self,
        base_url: str,
        main_markdown: Optional[str],
    ) -> list[tuple[str, str]]:
        """Find event page URLs from known patterns and main page links."""
        parsed = urlparse(base_url)
        base_normalized = base_url.rstrip("/")
        candidates: dict[str, str] = {}

        for path, label in EVENT_PAGE_PATTERNS:
            candidate = urljoin(base_normalized + "/", path.lstrip("/"))
            norm = candidate.rstrip("/")
            if norm not in candidates:
                candidates[norm] = label

        if main_markdown:
            for match in _LINK_RE.finditer(main_markdown):
                link_text = match.group(1).strip()
                href = match.group(2)
                full_url = urljoin(
                    f"{parsed.scheme}://{parsed.netloc}", href,
                ).rstrip("/")

                if full_url in candidates:
                    continue

                path_lower = href.lower()
                text_lower = link_text.lower()
                is_event_page = any(
                    kw in path_lower or kw in text_lower
                    for kw in ("news", "novosti", "afisha", "events", "meropriyat",
                               "anonsy", "press", "sobytiy")
                )
                if is_event_page:
                    candidates[full_url] = link_text or href

        return list(candidates.items())

    def _split_into_events(
        self,
        markdown: str,
        page_url: str,
        page_label: str,
    ) -> list[EventCandidate]:
        """
        Split a news/events feed page into individual event entries.

        Strategy:
          1. Split by headings (## or ###) — each heading = potential event
          2. Filter by freshness (≤ N days) and event keywords
          3. Return up to max_events_per_page candidates
        """
        sections = self._split_by_headings(markdown)

        candidates: list[EventCandidate] = []
        cutoff = datetime.now() - timedelta(days=self.freshness_days)

        for title, content in sections:
            if self._is_irrelevant(title, content):
                continue

            freshness = self._estimate_freshness(content)
            if freshness is not None and freshness > self.freshness_days:
                continue

            full_text = f"# {title}\n\n{content}".strip()
            if len(full_text) < 50:
                continue

            has_event_signal = self._has_event_signal(title, content)
            if not has_event_signal:
                continue

            candidates.append(EventCandidate(
                url=page_url,
                title=title.strip(),
                markdown=full_text[:8000],
                discovered_from=page_label,
                freshness_days=freshness,
            ))

            if len(candidates) >= self.max_events_per_page:
                break

        return candidates

    def _split_by_headings(self, markdown: str) -> list[tuple[str, str]]:
        """Split markdown into (heading, content) pairs by ## or ### headings."""
        heading_re = re.compile(r'^(#{2,3})\s+(.+)$', re.MULTILINE)
        positions = [(m.start(), m.group(2)) for m in heading_re.finditer(markdown)]

        if not positions:
            lines = markdown.split('\n')
            block_sections = self._split_by_separators(markdown)
            if block_sections:
                return block_sections
            return [("Запись", markdown)] if len(markdown.strip()) > 100 else []

        sections: list[tuple[str, str]] = []
        for i, (pos, title) in enumerate(positions):
            heading_end = markdown.index('\n', pos) + 1 if '\n' in markdown[pos:] else len(markdown)
            next_pos = positions[i + 1][0] if i + 1 < len(positions) else len(markdown)
            content = markdown[heading_end:next_pos].strip()
            sections.append((title, content))

        return sections

    def _split_by_separators(self, markdown: str) -> list[tuple[str, str]]:
        """Fallback: split by horizontal rules (---) or double newlines with date markers."""
        parts = re.split(r'\n---+\n|\n\n(?=\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|'
                         r'июля|августа|сентября|октября|ноября|декабря))',
                         markdown, flags=re.IGNORECASE)
        sections: list[tuple[str, str]] = []
        for part in parts:
            part = part.strip()
            if len(part) < 50:
                continue
            first_line = part.split('\n')[0].strip()
            title = first_line[:120] if first_line else "Запись"
            sections.append((title, part))
        return sections

    def _is_irrelevant(self, title: str, content: str) -> bool:
        combined = (title + " " + content[:300]).lower()
        return any(marker in combined for marker in IRRELEVANT_MARKERS)

    def _has_event_signal(self, title: str, content: str) -> bool:
        """Check for event-related keywords in title or beginning of content."""
        combined = (title + " " + content[:500]).lower()
        return any(kw in combined for kw in EVENT_KEYWORDS)

    def _estimate_freshness(self, content: str) -> Optional[int]:
        """Estimate how many days ago the content was published, or None if unknown."""
        match = _DATE_RE.search(content[:500])
        if not match:
            return None

        day = int(match.group(1))
        month_str = match.group(2)
        year_str = match.group(3)

        if month_str in _MONTH_MAP:
            month = _MONTH_MAP[month_str]
        else:
            try:
                month = int(month_str)
            except ValueError:
                return None

        year = int(year_str) if year_str else datetime.now().year

        try:
            pub_date = datetime(year, month, day)
            delta = datetime.now() - pub_date
            return max(0, delta.days)
        except ValueError:
            return None

    def _label_for_url(self, url: str) -> str:
        path = urlparse(url).path.lower()
        for pattern, label in EVENT_PAGE_PATTERNS:
            if pattern in path:
                return label
        return "Новости"
