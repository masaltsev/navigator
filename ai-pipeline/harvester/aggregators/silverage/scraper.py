"""Web scraper for silveragemap.ru (Silver Age Alliance).

Scrapes two sections:
  1. Practices (База практик) - paginated list + detail pages
  2. Events (Мероприятия) - single page + detail pages

Uses httpx + BeautifulSoup (the site is server-rendered HTML, no SPA).
Rate-limited to be respectful (1-2 sec between requests).
"""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

import httpx
import structlog
from bs4 import BeautifulSoup

from aggregators.silverage.models import SilverAgeEvent, SilverAgePractice

logger = structlog.get_logger(__name__)

BASE_URL = "https://silveragemap.ru"
PRACTICES_LIST_URL = f"{BASE_URL}/poisk-proekta/"
EVENTS_LIST_URL = f"{BASE_URL}/meropriyatiya/"

_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Navigator-Harvester/1.0"


class SilverAgeScraper:
    """Scraper for silveragemap.ru practices and events."""

    def __init__(
        self,
        delay: float = 1.5,
        timeout: float = 20.0,
        cache_dir: Optional[str] = None,
    ):
        self._delay = delay
        self._timeout = timeout
        self._cache_dir = Path(cache_dir) if cache_dir else None
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def scrape_all_practice_slugs(
        self,
        max_pages: Optional[int] = None,
    ) -> list[str]:
        """Scrape all practice slugs from the paginated list."""
        slugs: list[str] = []
        page = 1

        while True:
            if max_pages and page > max_pages:
                break

            url = PRACTICES_LIST_URL if page == 1 else f"{PRACTICES_LIST_URL}?PAGEN_1={page}"
            html = await self._fetch(url)
            if not html:
                break

            page_slugs = self._parse_practice_list(html)
            if not page_slugs:
                break

            slugs.extend(page_slugs)
            logger.info("Scraped practice list page", page=page, found=len(page_slugs), total=len(slugs))

            max_page = self._find_max_page(html)
            if page >= max_page:
                break

            page += 1
            await asyncio.sleep(self._delay)

        logger.info("All practice slugs scraped", total=len(slugs))
        return slugs

    async def scrape_practice_detail(self, slug: str) -> Optional[SilverAgePractice]:
        """Scrape a single practice detail page."""
        cached = self._load_cache("practice", slug)
        if cached:
            return SilverAgePractice.model_validate(cached)

        url = f"{PRACTICES_LIST_URL}{slug}/"
        html = await self._fetch(url)
        if not html:
            return None

        practice = self._parse_practice_detail(html, slug)
        if practice:
            self._save_cache("practice", slug, practice.model_dump())

        return practice

    async def scrape_all_practices(
        self,
        max_pages: Optional[int] = None,
        max_practices: Optional[int] = None,
    ) -> list[SilverAgePractice]:
        """Scrape all practices: list pages -> detail pages."""
        slugs = await self.scrape_all_practice_slugs(max_pages=max_pages)

        if max_practices:
            slugs = slugs[:max_practices]

        practices: list[SilverAgePractice] = []
        for i, slug in enumerate(slugs):
            logger.info("Scraping practice detail", progress=f"{i+1}/{len(slugs)}", slug=slug)
            practice = await self.scrape_practice_detail(slug)
            if practice:
                practices.append(practice)

            if i < len(slugs) - 1:
                await asyncio.sleep(self._delay)

        logger.info("All practices scraped", total=len(practices))
        return practices

    async def scrape_all_events(self) -> list[SilverAgeEvent]:
        """Scrape all events from the events page + detail pages."""
        html = await self._fetch(EVENTS_LIST_URL)
        if not html:
            return []

        event_slugs = self._parse_events_list(html)
        logger.info("Event slugs found", count=len(event_slugs))

        events: list[SilverAgeEvent] = []
        for i, slug in enumerate(event_slugs):
            logger.info("Scraping event detail", progress=f"{i+1}/{len(event_slugs)}", slug=slug)
            event = await self._scrape_event_detail(slug)
            if event:
                events.append(event)

            if i < len(event_slugs) - 1:
                await asyncio.sleep(self._delay)

        logger.info("All events scraped", total=len(events))
        return events

    # ------------------------------------------------------------------
    # HTML parsing: practice list
    # ------------------------------------------------------------------

    def _parse_practice_list(self, html: str) -> list[str]:
        """Extract practice slugs from a list page."""
        slugs: list[str] = []
        pattern = re.compile(r"href=['\"]?/poisk-proekta/([a-z0-9][a-z0-9-]+)/['\"]?")
        for match in pattern.finditer(html):
            slug = match.group(1)
            if slug not in ("form", "search"):
                slugs.append(slug)
        return list(dict.fromkeys(slugs))

    def _find_max_page(self, html: str) -> int:
        pages = re.findall(r"PAGEN_1=(\d+)", html)
        if pages:
            return max(int(p) for p in pages)
        return 1

    # ------------------------------------------------------------------
    # HTML parsing: practice detail
    # ------------------------------------------------------------------

    def _parse_practice_detail(self, html: str, slug: str) -> Optional[SilverAgePractice]:
        """Parse a practice detail page into SilverAgePractice."""
        soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.select_one("h1")
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)

        region = ""
        region_el = soup.select_one(".region")
        if region_el:
            region = region_el.get_text(strip=True)

        dates = ""
        date_el = soup.select_one(".data")
        if date_el:
            dates = date_el.get_text(strip=True)

        categories = self._extract_categories(soup)

        description = ""
        main_content = soup.select_one(".content")
        if main_content:
            for child in main_content.find_all(["script", "style", "nav"]):
                child.decompose()
            for icon_c in main_content.select(".icon_project_container"):
                icon_c.decompose()
            for ri in main_content.select(".region_info"):
                ri.decompose()
            description = main_content.get_text(separator="\n", strip=True)
            description = re.sub(r"\n{3,}", "\n\n", description)

        org_info = self._extract_org_info(html)

        return SilverAgePractice(
            slug=slug,
            title=title,
            short_description=description[:200] if description else "",
            full_description=description,
            region=region,
            categories=categories,
            dates=dates,
            page_url=f"{PRACTICES_LIST_URL}{slug}/",
            **org_info,
        )

    def _extract_categories(self, soup: BeautifulSoup) -> list[str]:
        """Extract category tags from icon classes (first container only)."""
        category_map = {
            "backcolor_health": "Здоровый образ жизни",
            "backcolor_educ": "Обучение",
            "backcolor_business": "Взаимопомощь",
            "backcolor_care": "Забота рядом",
            "backcolor_sport": "Связь поколений",
            "backcolor_art": "Культура и искусство",
            "backcolor_nature": "История и краеведение",
            "backcolor_tech": "Психология",
        }
        first_container = soup.select_one(".icon_project_container")
        if not first_container:
            return []
        categories: list[str] = []
        for cls, name in category_map.items():
            if first_container.select_one(f".icon_project.{cls}"):
                categories.append(name)
        return categories

    def _extract_org_info(self, html: str) -> dict:
        """Extract org info from the info_popup div."""
        result = {
            "org_name": "",
            "org_description": "",
            "org_email": "",
            "org_phone": "",
            "org_website": None,
            "org_vk": None,
            "org_social_links": [],
        }

        match = re.search(
            r"id=['\"]info_popup['\"]>(.*?)</div>",
            html,
            re.DOTALL,
        )
        if not match:
            return result

        raw_text = match.group(1).strip()
        raw_text = re.sub(r"<[^>]+>", "\n", raw_text)
        raw_text = re.sub(r"\n{2,}", "\n", raw_text).strip()

        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
        if not lines:
            return result

        desc_lines: list[str] = []
        contact_lines: list[str] = []
        for line in lines:
            if re.match(r"^[\w.+-]+@[\w.-]+\.\w+$", line):
                result["org_email"] = line
            elif re.match(r"^\+?\d[\d\s()-]+$", line):
                result["org_phone"] = line
            elif re.match(r"^https?://", line):
                url = line.strip()
                social_domains = (
                    "vk.com", "vkontakte", "ok.ru", "odnoklassniki",
                    "t.me", "telegram", "max.ru",
                    "youtube.com", "rutube.ru", "zen.yandex",
                    "instagram.com", "facebook.com",
                )
                if "vk.com" in url or "vkontakte" in url:
                    result["org_vk"] = url
                    result["org_social_links"].append(url)
                elif any(d in url for d in social_domains):
                    result["org_social_links"].append(url)
                else:
                    result["org_social_links"].append(url)
                    if not result["org_website"]:
                        result["org_website"] = url
            else:
                desc_lines.append(line)

        if desc_lines:
            full_text = " ".join(desc_lines)
            first_sentence_end = re.search(r"[.!?]\s", full_text)
            if first_sentence_end and first_sentence_end.start() < 200:
                result["org_name"] = full_text[: first_sentence_end.start() + 1].strip()
            else:
                words = full_text.split()
                if len(words) <= 15:
                    result["org_name"] = full_text
                else:
                    for marker in ("»", ")", '"'):
                        idx = full_text.find(marker)
                        if 5 < idx < 200:
                            result["org_name"] = full_text[: idx + 1].strip()
                            break
                    else:
                        result["org_name"] = " ".join(words[:10])

            result["org_description"] = full_text

        return result

    # ------------------------------------------------------------------
    # HTML parsing: events
    # ------------------------------------------------------------------

    def _parse_events_list(self, html: str) -> list[str]:
        slugs: list[str] = []
        pattern = re.compile(r"href=['\"]?/meropriyatiya/([a-z0-9][a-z0-9-]+)/['\"]?")
        for match in pattern.finditer(html):
            slug = match.group(1)
            slugs.append(slug)
        return list(dict.fromkeys(slugs))

    async def _scrape_event_detail(self, slug: str) -> Optional[SilverAgeEvent]:
        cached = self._load_cache("event", slug)
        if cached:
            return SilverAgeEvent.model_validate(cached)

        url = f"{EVENTS_LIST_URL}{slug}/"
        html = await self._fetch(url)
        if not html:
            return None

        event = self._parse_event_detail(html, slug)
        if event:
            self._save_cache("event", slug, event.model_dump())

        return event

    def _parse_event_detail(self, html: str, slug: str) -> Optional[SilverAgeEvent]:
        soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.select_one(".titlePage") or soup.select_one("h1")
        if not title_tag:
            return None

        title = title_tag.get_text(strip=True)

        location = ""
        for text_el in soup.find_all(string=re.compile(r"Место проведения")):
            parent = text_el.find_parent()
            if parent:
                next_el = parent.find_next_sibling()
                if next_el:
                    location = next_el.get_text(strip=True)
                    break

        date_text = ""
        for text_el in soup.find_all(string=re.compile(r"Сроки проведения")):
            parent = text_el.find_parent()
            if parent:
                next_el = parent.find_next_sibling()
                if next_el:
                    date_text = next_el.get_text(strip=True)
                    break

        category = ""
        cat_tag = soup.select_one(".newsTag")
        if cat_tag:
            category = cat_tag.get_text(strip=True)

        description = ""
        content = soup.select_one(".containerProject-content")
        if content:
            description = content.get_text(separator="\n", strip=True)
            description = re.sub(r"\n{3,}", "\n\n", description)

        reg_url = None
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(d in href for d in ("timepad.ru", "nethouse.ru", "ticketscloud")):
                reg_url = href
                break
            if "записаться" in a.get_text(strip=True).lower():
                reg_url = href
                break

        page_url = f"{EVENTS_LIST_URL}{slug}/"

        return SilverAgeEvent(
            slug=slug,
            title=title,
            date_text=date_text,
            location=location,
            description=description[:2000],
            category=category,
            page_url=page_url,
            registration_url=reg_url,
        )

    # ------------------------------------------------------------------
    # HTTP + caching
    # ------------------------------------------------------------------

    async def _fetch(self, url: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                verify=False,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning("HTTP error", url=url, status=resp.status_code)
                    return None
                return resp.text
        except Exception as e:
            logger.error("Fetch error", url=url, error=str(e))
            return None

    def _cache_key(self, kind: str, slug: str) -> Path:
        if not self._cache_dir:
            raise ValueError("No cache dir")
        subdir = self._cache_dir / kind
        subdir.mkdir(parents=True, exist_ok=True)
        return subdir / f"{slug}.json"

    def _load_cache(self, kind: str, slug: str) -> Optional[dict]:
        if not self._cache_dir:
            return None
        path = self._cache_key(kind, slug)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    def _save_cache(self, kind: str, slug: str, data: dict) -> None:
        if not self._cache_dir:
            return
        path = self._cache_key(kind, slug)
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning("Cache save failed", error=str(e))
