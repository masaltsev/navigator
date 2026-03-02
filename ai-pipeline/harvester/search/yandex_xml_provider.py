"""Yandex Cloud Search API v2 provider.

Note: This is Yandex Cloud Search API (searchapi.api.cloud.yandex.net), not the
public ya.ru search. Ranking and results can differ from what you see in a
browser on ya.ru/search — different product, different index.

Setup (Yandex Cloud Console):
  1. Create service account with role "admin"
  2. Create API key with scope "yc.search-api.execute"
  3. Enable Search API in the folder, set search type to "Russian"

Env vars:
  YANDEX_SEARCH_FOLDER_ID  — folder ID from Yandex Cloud console
  YANDEX_SEARCH_API_KEY    — API key (NOT OAuth token)

Pricing (since March 2025):
  - Sync queries:  480 RUB / 1 000 requests
  - Async queries: cheaper but results arrive in hours

API flow:
  POST /v2/web/searchAsync  → operation_id
  GET  /operations/{id}     → poll until done → base64-encoded XML
"""

import asyncio
import base64
import json
import re
import time
from typing import Optional
from xml.etree import ElementTree

import httpx
import structlog

from config.settings import get_settings
from search.provider import SearchResult, WebSearchProvider

logger = structlog.get_logger(__name__)

_SEARCH_URL = "https://searchapi.api.cloud.yandex.net/v2/web/searchAsync"
_OPERATION_URL = "https://operation.api.cloud.yandex.net/operations/"
_INTER_QUERY_DELAY = 0.5

# Yandex region IDs (lr) for Russian regions — improves ranking for local orgs.
# See https://yandex.com/dev/xml/doc/en/reference/regions
REGION_NAME_TO_LR: dict[str, int] = {
    "москва": 213,
    "московская область": 1,
    "санкт-петербург": 2,
    "ленинградская область": 101,
    "костромская область": 44,
    "вологодская область": 35,
    "воронежская область": 36,
    "нижегородская область": 47,
    "россия": 225,
}

# ISO 3166-2 (e.g. RU-MOW) → Russian name for search/LLM context when API returns region_iso
REGION_ISO_TO_NAME: dict[str, str] = {
    "RU-MOW": "Москва",
    "RU-MOS": "Московская область",
    "RU-SPE": "Санкт-Петербург",
    "RU-LEN": "Ленинградская область",
    "RU-KOS": "Костромская область",
    "RU-VLG": "Вологодская область",
    "RU-VOR": "Воронежская область",
    "RU-NIZ": "Нижегородская область",
    "RU-MUR": "Мурманская область",
    "RU-BRY": "Брянская область",
    "RU-SVE": "Свердловская область",
    "RU-TYU": "Тюменская область",
    "RU-NEN": "Ненецкий АО",
    "RU-YAR": "Ярославская область",
    "RU-IVA": "Ивановская область",
    "RU-TUL": "Тульская область",
    "RU-ROS": "Ростовская область",
    "RU-KDA": "Краснодарский край",
    "RU-ZAB": "Забайкальский край",
    "RU-KEM": "Кемеровская область",
    "RU-NVS": "Новосибирская область",
}


def region_name_to_yandex_lr(region_name: str) -> Optional[int]:
    """Map region name (e.g. 'Костромская область' or 'Костромская область, Кострома') to Yandex lr id."""
    if not region_name or not isinstance(region_name, str):
        return None
    key = region_name.strip().lower()
    lr = REGION_NAME_TO_LR.get(key)
    if lr is not None:
        return lr
    # "Region, City" → try region part only
    if "," in key:
        key = key.split(",")[0].strip()
        return REGION_NAME_TO_LR.get(key)
    return None


def _city_from_address(address_raw: Optional[str]) -> str:
    """Extract city (or settlement) from venue address_raw for geo context.
    Prefer «г. Город» / «город Город»; else first part before comma if it looks like a place.
    """
    if not address_raw or not isinstance(address_raw, str):
        return ""
    s = address_raw.strip()
    if not s:
        return ""
    # г. Москва, г. Кострома, город Вологда
    m = re.search(r"(?:г\.?|город)\s+([А-Яа-яёЁ\-]+(?:\s+[А-Яа-яёЁ\-]+)?)\s*(?:,|$)", s, re.UNICODE)
    if m:
        return m.group(1).strip()
    # First segment before comma (e.g. "Москва, ул. ..." or "Вологда, ...")
    m = re.match(r"^([А-Яа-яёЁ\-]+(?:\s+[А-Яа-яёЁ\-]+)?)\s*,", s, re.UNICODE)
    if m:
        return m.group(1).strip()
    return ""


def region_from_api(
    region_iso: Optional[str] = None,
    region_code: Optional[str] = None,
    address_raw: Optional[str] = None,
) -> str:
    """Build one geo string (region and/or city) for search, Dadata and LLM.

    Ideally contains both region and city to disambiguate same-name orgs (e.g. «Милосердие»).
    Uses region_iso → region name; optionally extracts city from venue address_raw.
    """
    region_name = ""
    if region_iso:
        region_name = REGION_ISO_TO_NAME.get((region_iso or "").strip().upper()) or (region_iso or "").strip()
    if not region_name and region_code:
        region_name = (region_code or "").strip()
    city = _city_from_address(address_raw)
    if region_name and city and city.lower() != region_name.lower():
        return f"{region_name}, {city}"
    return region_name or city or ""


def split_geo_for_search(geo: str) -> tuple[str, str]:
    """Split geo string into part for search query (prefer city) and for Yandex lr (region).

    When geo is "Region, City" (e.g. "Костромская область, Кострома"):
      - query_part: city for more specific search query text
      - lr_part: region for Yandex region_id (lr)
    When geo is single (region or city): both parts equal.
    """
    if not geo or not isinstance(geo, str):
        return "", ""
    s = geo.strip()
    if "," in s:
        region_part, city_part = s.split(",", 1)
        region_part = region_part.strip()
        city_part = city_part.strip()
        return (city_part or region_part, region_part or city_part)
    return (s, s)


def _strip_hl(text: str) -> str:
    """Remove <hlword> highlight tags from Yandex XML text."""
    return re.sub(r"</?hlword>", "", text)


class YandexSearchProvider(WebSearchProvider):
    """Web search via Yandex Cloud Search API v2.

    Direct HTTP integration — no third-party SDK required.
    Auth: Api-Key header with service account API key (scope yc.search-api.execute).
    """

    def __init__(
        self,
        folder_id: str = "",
        api_key: str = "",
        max_wait: int = 60,
        poll_interval: float = 1.0,
        timeout: float = 15.0,
    ) -> None:
        super().__init__()
        settings = get_settings()
        self._folder_id = folder_id or settings.yandex_search_folder_id
        self._api_key = api_key or settings.yandex_search_api_key
        self._max_wait = max_wait
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._last_query_at: float = 0.0

        if not self.is_configured:
            logger.warning(
                "yandex_provider_no_credentials",
                msg="YANDEX_SEARCH_FOLDER_ID / YANDEX_SEARCH_API_KEY not set",
            )

    @property
    def engine_name(self) -> str:
        return "yandex"

    @property
    def is_configured(self) -> bool:
        return bool(self._folder_id and self._api_key)

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Api-Key {self._api_key}",
            "Content-Type": "application/json",
        }

    async def search(
        self,
        query: str,
        *,
        num_results: int = 10,
        region: str = "ru-ru",
        region_id: Optional[int] = None,
    ) -> list[SearchResult]:
        if not self.is_configured:
            raise RuntimeError(
                "YandexSearchProvider requires YANDEX_SEARCH_FOLDER_ID and "
                "YANDEX_SEARCH_API_KEY. Create a service account with "
                "scope yc.search-api.execute in Yandex Cloud Console."
            )

        await self._rate_limit()

        t0 = time.monotonic()
        try:
            xml_text = await self._search_and_wait(query, num_results, region_id)
            results = _parse_yandex_xml(xml_text)
            elapsed = time.monotonic() - t0
            self.stats.record(len(results), elapsed)
            logger.info(
                "yandex_search",
                query=query[:80],
                results=len(results),
                elapsed=round(elapsed, 2),
                region_id=region_id,
            )
            return results
        except TimeoutError as exc:
            elapsed = time.monotonic() - t0
            self.stats.record(0, elapsed, error=True)
            logger.warning(
                "yandex_search_timeout", query=query[:80], elapsed=round(elapsed, 2)
            )
            return []
        except Exception as exc:
            elapsed = time.monotonic() - t0
            self.stats.record(0, elapsed, error=True)
            logger.warning(
                "yandex_search_error", query=query[:80], error=str(exc)
            )
            raise

    async def _search_and_wait(
        self, query: str, num_results: int, region_id: Optional[int] = None
    ) -> str:
        """Submit async search, poll for completion, return XML."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            operation_id = await self._submit_search(
                client, query, num_results, region_id
            )
            return await self._poll_operation(client, operation_id)

    async def _submit_search(
        self,
        client: httpx.AsyncClient,
        query: str,
        num_results: int,
        region_id: Optional[int] = None,
    ) -> str:
        body = {
            "query": {
                "searchType": "SEARCH_TYPE_RU",
                "queryText": query,
                "page": 0,
            },
            "groupSpec": {
                "groupsOnPage": min(num_results, 100),
                "docsInGroup": 1,
            },
            "l10N": "ru",
            "folderId": self._folder_id,
            "responseFormat": "FORMAT_XML",
        }
        if region_id is not None:
            body["query"]["regionId"] = region_id

        resp = await client.post(
            _SEARCH_URL,
            headers=self._auth_headers(),
            content=json.dumps(body),
        )
        resp.raise_for_status()
        data = resp.json()

        operation_id = data.get("id")
        if not operation_id:
            raise RuntimeError(f"Yandex Search: no operation id in response: {data}")

        logger.debug("yandex_search_submitted", operation_id=operation_id)
        return operation_id

    async def _poll_operation(self, client: httpx.AsyncClient, operation_id: str) -> str:
        """Poll operation endpoint until done or timeout."""
        deadline = time.monotonic() + self._max_wait

        while time.monotonic() < deadline:
            resp = await client.get(
                f"{_OPERATION_URL}{operation_id}",
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("done"):
                if "error" in data:
                    err = data["error"]
                    raise RuntimeError(
                        f"Yandex Search operation failed: "
                        f"[{err.get('code')}] {err.get('message', '')}"
                    )
                raw_b64 = data.get("response", {}).get("rawData", "")
                if not raw_b64:
                    raise RuntimeError("Yandex Search: no rawData in response")
                return base64.b64decode(raw_b64).decode("utf-8")

            await asyncio.sleep(self._poll_interval)

        raise TimeoutError(
            f"Yandex Search: operation {operation_id} not done after {self._max_wait}s"
        )

    async def _rate_limit(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_query_at
        if elapsed < _INTER_QUERY_DELAY and self._last_query_at > 0:
            await asyncio.sleep(_INTER_QUERY_DELAY - elapsed)
        self._last_query_at = time.monotonic()


def _parse_yandex_xml(xml_text: str) -> list[SearchResult]:
    """Parse Yandex Search XML response into SearchResult list."""
    root = ElementTree.fromstring(xml_text)

    error = root.find(".//response/error")
    if error is not None:
        code = error.get("code", "?")
        msg = (error.text or "").strip()
        if code == "15":
            return []
        raise RuntimeError(f"Yandex Search error {code}: {msg}")

    results: list[SearchResult] = []
    position = 0

    for group in root.findall(".//response/results/grouping/group"):
        for doc in group.findall("doc"):
            position += 1
            url_el = doc.find("url")
            title_el = doc.find("title")
            passages_el = doc.find("passages")

            url = (url_el.text or "").strip() if url_el is not None else ""
            title = _strip_hl(
                ElementTree.tostring(title_el, encoding="unicode", method="text")
                if title_el is not None
                else ""
            ).strip()

            snippet_parts = []
            if passages_el is not None:
                for passage in passages_el.findall("passage"):
                    text = ElementTree.tostring(
                        passage, encoding="unicode", method="text"
                    )
                    snippet_parts.append(_strip_hl(text).strip())
            snippet = " ".join(snippet_parts)

            if url:
                results.append(
                    SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        position=position,
                        source_engine="yandex",
                    )
                )

    return results
