"""Scraper for individual FPG project card detail pages.

URL pattern: /public/application/item?id={UUID}

The detail page (Vue.js SPA) contains data not in the XLSX:
- Organization website URL (often "нет"/empty)
- Full project description, goals, tasks
- Geography (detailed scope)
- Target groups
- Organization address

Since the FPG site uses anti-bot protection (MYRTEX), this scraper
uses Crawl4AI with Playwright for rendering.

This scraper is secondary to the main pipeline: the XLSX already
has INN/OGRN/region/title. The scraper adds project descriptions
and (rare) org website URLs.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

FPG_BASE_URL = "https://xn--80afcdbalict6afooklqi5o.xn--p1ai"
CARD_URL_TEMPLATE = f"{FPG_BASE_URL}/public/application/item?id={{uuid}}"
CARDS_LIST_URL = f"{FPG_BASE_URL}/public/application/cards"


class FPGCardData:
    """Parsed data from an FPG project card page."""

    def __init__(self) -> None:
        self.project_title: str = ""
        self.org_name: str = ""
        self.org_website: Optional[str] = None
        self.description: str = ""
        self.goals: str = ""
        self.social_significance: str = ""
        self.geography: str = ""
        self.target_groups: str = ""
        self.org_address: str = ""
        self.inn: str = ""
        self.ogrn: str = ""

    def to_dict(self) -> dict:
        return {
            "project_title": self.project_title,
            "org_name": self.org_name,
            "org_website": self.org_website,
            "description": self.description,
            "goals": self.goals,
            "social_significance": self.social_significance,
            "geography": self.geography,
            "target_groups": self.target_groups,
            "org_address": self.org_address,
            "inn": self.inn,
            "ogrn": self.ogrn,
        }

    @property
    def has_website(self) -> bool:
        return bool(self.org_website) and self.org_website.lower() not in ("нет", "")


class FPGCardScraper:
    """Scraper for FPG project cards using Crawl4AI."""

    def __init__(self, cache_dir: Optional[str] = None):
        self._cache_dir = Path(cache_dir) if cache_dir else None
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def scrape_card(self, card_uuid: str) -> Optional[FPGCardData]:
        """Scrape a single FPG project card by UUID."""
        cached = self._load_cache(card_uuid)
        if cached:
            return cached

        url = CARD_URL_TEMPLATE.format(uuid=card_uuid)
        logger.info("Scraping FPG card", uuid=card_uuid, url=url)

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

            from config.settings import get_settings

            browser_config = BrowserConfig(
                headless=True,
                user_data_dir=get_settings().get_crawl4ai_browser_data_dir(),
            )
            run_config = CrawlerRunConfig(
                wait_until="networkidle",
                page_timeout=30000,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=url, config=run_config)

                if not result.success:
                    logger.warning("Failed to scrape FPG card", uuid=card_uuid)
                    return None

                data = self._parse_markdown(result.markdown_v2.raw_markdown)
                self._save_cache(card_uuid, data)
                return data

        except ImportError:
            logger.warning("crawl4ai not available, skipping card scrape")
            return None
        except Exception as e:
            logger.error("Error scraping FPG card", uuid=card_uuid, error=str(e))
            return None

    async def search_card_uuid(self, application_number: str) -> Optional[str]:
        """Try to find the UUID for a project by its application number.

        The FPG catalog uses UUIDs in URLs but XLSX has application numbers.
        We search the catalog and try to match.
        """
        query = application_number.replace("-", " ")
        search_url = f"{CARDS_LIST_URL}?SearchString={application_number}"

        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

            from config.settings import get_settings

            browser_config = BrowserConfig(
                headless=True,
                user_data_dir=get_settings().get_crawl4ai_browser_data_dir(),
            )
            run_config = CrawlerRunConfig(
                wait_until="networkidle",
                page_timeout=30000,
            )

            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=search_url, config=run_config)

                if not result.success:
                    return None

                uuid_pattern = re.compile(
                    r"/public/application/item\?id=([a-f0-9-]{36})"
                )
                match = uuid_pattern.search(result.html or "")
                if match:
                    return match.group(1)

        except Exception as e:
            logger.warning(
                "Error searching FPG card UUID",
                app_number=application_number,
                error=str(e),
            )
        return None

    def _parse_markdown(self, markdown: str) -> FPGCardData:
        """Extract structured data from the card page markdown."""
        data = FPGCardData()

        section_patterns = {
            "description": r"(?:Краткое описание|Описание проекта)[:\s]*\n(.*?)(?=\n#{1,3}\s|\n\*\*[А-Я]|\Z)",
            "goals": r"(?:Цель|Цели проекта)[:\s]*\n(.*?)(?=\n#{1,3}\s|\n\*\*[А-Я]|\Z)",
            "social_significance": r"(?:Обоснование социальной значимости)[:\s]*\n(.*?)(?=\n#{1,3}\s|\n\*\*[А-Я]|\Z)",
            "geography": r"(?:География проекта)[:\s]*\n(.*?)(?=\n#{1,3}\s|\n\*\*[А-Я]|\Z)",
            "target_groups": r"(?:Целевые группы)[:\s]*\n(.*?)(?=\n#{1,3}\s|\n\*\*[А-Я]|\Z)",
        }

        for field_name, pattern in section_patterns.items():
            match = re.search(pattern, markdown, re.DOTALL | re.IGNORECASE)
            if match:
                setattr(data, field_name, match.group(1).strip())

        website_match = re.search(
            r"(?:Веб-сайт|Сайт)[:\s]*(https?://\S+)", markdown, re.IGNORECASE
        )
        if website_match:
            data.org_website = website_match.group(1).rstrip(")")

        inn_match = re.search(r"ИНН[:\s]*(\d{10,12})", markdown)
        if inn_match:
            data.inn = inn_match.group(1)

        ogrn_match = re.search(r"ОГРН[:\s]*(\d{13,15})", markdown)
        if ogrn_match:
            data.ogrn = ogrn_match.group(1)

        return data

    def _cache_key(self, uuid: str) -> Path:
        if not self._cache_dir:
            raise ValueError("No cache dir configured")
        return self._cache_dir / f"{uuid}.json"

    def _load_cache(self, uuid: str) -> Optional[FPGCardData]:
        if not self._cache_dir:
            return None
        path = self._cache_key(uuid)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
            data = FPGCardData()
            for k, v in raw.items():
                if hasattr(data, k):
                    setattr(data, k, v)
            logger.debug("FPG card cache hit", uuid=uuid)
            return data
        except Exception:
            return None

    def _save_cache(self, uuid: str, data: FPGCardData) -> None:
        if not self._cache_dir:
            return
        path = self._cache_key(uuid)
        try:
            path.write_text(json.dumps(data.to_dict(), ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("Failed to save FPG card cache", error=str(e))
