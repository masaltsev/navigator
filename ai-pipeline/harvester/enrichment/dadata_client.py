"""
Dadata geocoding client for Harvester.

Resolves raw addresses → fias_id (settlement/city level), city_fias_id,
region_iso, coordinates for VenuePayload.

Also provides findPartyById for organization verification by INN/OGRN.

Priority:
  1. Suggest API (suggestions.dadata.ru) — free tier 10K/day, default.
  2. Clean API  (cleaner.dadata.ru)      — paid per call, opt-in via use_clean=True.

Uses httpx for async HTTP. Gracefully degrades when keys are missing
(returns the original address unchanged).

IMPORTANT: fias_id logic mirrors backend/app/Services/VenueAddressEnricher/
  - fias_id stored = settlement_fias_id → city_fias_id → region_fias_id
  - city_fias_id: from data, or resolved from address text, or fallback by level
  - Federal cities (RU-MOW, RU-SPE, RU-SEV): city_fias_id = fias_id when level=1
  - New regions without ISO (LNR, DNR, etc.): region_code = region_fias_id
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx
import structlog
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)
_stdlib_logger = logging.getLogger(__name__)

DADATA_CLEAN_URL = "https://cleaner.dadata.ru/api/v1/clean/address"
DADATA_SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/address"
DADATA_FIND_PARTY_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
DADATA_SUGGEST_PARTY_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"

FEDERAL_CITY_ISOS = frozenset({"RU-MOW", "RU-SPE", "RU-SEV"})

_CITY_RE = re.compile(
    r"\b(?:г\.?|город)\s+([А-Яа-яёЁ\-]+(?:\s+[А-Яа-яёЁ\-]+)?)\s*(?:,|$)",
    re.UNICODE,
)
_FIRST_PART_RE = re.compile(
    r"^([А-Яа-яёЁ\-]+(?:\s+[А-Яа-яёЁ\-]+)?)\s*,",
    re.UNICODE,
)


@dataclass
class GeocodingResult:
    """
    Structured result from Dadata address resolution.

    fias_id: settlement/city/region level (NOT house/street) — matches
             what backend stores in venues.fias_id for city filtering.
    city_fias_id: for API filter "by city". May differ from fias_id
                  (e.g. fias_id=settlement, city_fias_id=parent city).
    """

    address_raw: str
    address_normalized: Optional[str] = None
    fias_id: Optional[str] = None
    fias_level: Optional[str] = None
    city_fias_id: Optional[str] = None
    kladr_id: Optional[str] = None
    region_iso: Optional[str] = None
    region_code: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    quality: Optional[str] = None


@dataclass
class PartyResult:
    """Result from Dadata findById/party or suggest/party."""

    found: bool = False
    inn: Optional[str] = None
    ogrn: Optional[str] = None
    kpp: Optional[str] = None
    name_full: Optional[str] = None
    name_short: Optional[str] = None
    opf: Optional[str] = None
    okved: Optional[str] = None
    director_name: Optional[str] = None
    director_post: Optional[str] = None
    address: Optional[str] = None
    address_unrestricted: Optional[str] = None
    city_fias_id: Optional[str] = None
    region_fias_id: Optional[str] = None
    region_iso: Optional[str] = None
    geo_lat: Optional[float] = None
    geo_lon: Optional[float] = None
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    status: Optional[str] = None
    raw_data: Optional[dict] = None

    def to_geocoding_result(self) -> "GeocodingResult":
        """Convert address portion to GeocodingResult (avoids a separate geocode call)."""
        addr_data = (self.raw_data or {}).get("address", {}).get("data", {})
        if not addr_data:
            return GeocodingResult(address_raw=self.address or "")
        return GeocodingResult(
            address_raw=self.address or "",
            address_normalized=self.address_unrestricted,
            fias_id=_pick_settlement_or_city_fias_id(addr_data),
            fias_level=_pick_fias_level(addr_data),
            city_fias_id=_str_or_none(addr_data.get("city_fias_id")),
            kladr_id=_pick_kladr_id(addr_data),
            region_iso=_str_or_none(addr_data.get("region_iso_code")),
            region_code=_pick_region_code(addr_data),
            geo_lat=_safe_float(addr_data.get("geo_lat")),
            geo_lon=_safe_float(addr_data.get("geo_lon")),
        )


class DadataClient:
    """
    Async Dadata client for address geocoding and organization lookup.

    Address geocoding:
      - **suggest** (suggestions.dadata.ru) — free tier 10K/day (more with
        subscription). Returns fias_id, coordinates. DEFAULT mode.
      - **clean** (cleaner.dadata.ru) — paid per call, higher accuracy,
        returns quality_code. Requires secret_key. Opt-in via use_clean=True.

    Organization lookup:
      - **findPartyById** — find organization by INN/OGRN. Returns name,
        address, contacts. Free tier. Uses suggest API endpoint.

    If api_key is not provided, all calls return passthrough/empty results.
    """

    def __init__(
        self,
        api_key: str = "",
        secret_key: str = "",
        timeout: float = 10.0,
        use_clean: bool = False,
    ):
        self._api_key = api_key
        self._secret_key = secret_key
        self._timeout = timeout
        self._enabled = bool(api_key)
        self._use_clean = use_clean and bool(secret_key)

        self._total_calls = 0
        self._successful = 0
        self._failed = 0

        if self._enabled:
            mode = "clean" if self._use_clean else "suggest"
            logger.info("DadataClient enabled, mode=%s", mode)

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------
    # Address geocoding
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        before_sleep=before_sleep_log(_stdlib_logger, logging.WARNING),
    )
    async def geocode(self, address_raw: str) -> GeocodingResult:
        """
        Geocode a single raw address string.

        Default: suggest API (free).
        If use_clean=True and secret_key set: clean API (paid, higher quality).
        Returns passthrough GeocodingResult if client is disabled.
        """
        if not self._enabled:
            return GeocodingResult(address_raw=address_raw)

        self._total_calls += 1

        try:
            if self._use_clean:
                data = await self._clean_address_raw(address_raw)
            else:
                data = await self._suggest_address_raw(address_raw)

            if data is None:
                # Suggest returned nothing — try clean as fallback if available
                if not self._use_clean and self._secret_key:
                    data = await self._clean_address_raw(address_raw)

            if data is None:
                return GeocodingResult(address_raw=address_raw)

            self._successful += 1
            return self._map_data_to_result(data, address_raw)

        except Exception as e:
            self._failed += 1
            logger.warning("Dadata geocode failed for '%s': %s", address_raw[:80], e)
            return GeocodingResult(address_raw=address_raw)

    async def geocode_batch(self, addresses: list[str]) -> list[GeocodingResult]:
        """Geocode multiple addresses sequentially (Dadata has no batch endpoint)."""
        results = []
        for addr in addresses:
            result = await self.geocode(addr)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Organization lookup
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        before_sleep=before_sleep_log(_stdlib_logger, logging.WARNING),
    )
    async def find_party_by_id(self, inn_or_ogrn: str) -> PartyResult:
        """
        Find organization by INN or OGRN via Dadata findById/party.
        Returns name, address, phones, emails.
        """
        if not self._enabled or not inn_or_ogrn.strip():
            return PartyResult()

        self._total_calls += 1

        try:
            headers = self._suggest_headers()
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    DADATA_FIND_PARTY_URL,
                    json={"query": inn_or_ogrn.strip(), "count": 1},
                    headers=headers,
                )
                resp.raise_for_status()

            body = resp.json()
            suggestions = body.get("suggestions", [])
            if not suggestions:
                return PartyResult()

            item = suggestions[0].get("data", {})
            self._successful += 1
            return self._parse_party(item)

        except Exception as e:
            self._failed += 1
            logger.warning("Dadata findParty failed for '%s': %s", inn_or_ogrn, e)
            return PartyResult()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        before_sleep=before_sleep_log(_stdlib_logger, logging.WARNING),
    )
    async def suggest_party(
        self,
        query: str,
        count: int = 3,
        region: Optional[str] = None,
    ) -> list[PartyResult]:
        """Search for organizations by name (+ optional region hint).

        Uses Dadata suggest/party endpoint (free tier, same as address suggest).
        Good for finding INN/OGRN when only organization name and city/region
        are known (e.g. Silver Age scraper data).

        Args:
            query: Organization name, optionally with city/region in text.
            count: Max results to return (1-20).
            region: Optional region name to filter results (e.g. "Вологодская").
        """
        if not self._enabled or not query.strip():
            return []

        self._total_calls += 1

        try:
            headers = self._suggest_headers()
            body: dict = {"query": query.strip(), "count": count}
            if region:
                body["locations"] = [{"region": region}]

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    DADATA_SUGGEST_PARTY_URL,
                    json=body,
                    headers=headers,
                )
                resp.raise_for_status()

            suggestions = resp.json().get("suggestions", [])
            if not suggestions:
                return []

            self._successful += 1
            return [
                self._parse_party(s.get("data", {}))
                for s in suggestions
                if s.get("data")
            ]

        except Exception as e:
            self._failed += 1
            logger.warning("Dadata suggest_party failed for '%s': %s", query[:60], e)
            return []

    # ------------------------------------------------------------------
    # Raw API calls
    # ------------------------------------------------------------------

    async def _suggest_address_raw(self, query: str) -> Optional[dict]:
        """Call suggest API, return raw data dict or None."""
        headers = self._suggest_headers()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                DADATA_SUGGEST_URL,
                json={"query": query, "count": 1},
                headers=headers,
            )
            resp.raise_for_status()

        body = resp.json()
        suggestions = body.get("suggestions", [])
        if not suggestions:
            return None
        return suggestions[0].get("data")

    async def _clean_address_raw(self, query: str) -> Optional[dict]:
        """Call clean API, return raw data dict or None."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {self._api_key}",
            "X-Secret": self._secret_key,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                DADATA_CLEAN_URL,
                json=[query],
                headers=headers,
            )
            resp.raise_for_status()

        data = resp.json()
        if not data or not isinstance(data, list):
            return None
        return data[0] if data[0] else None

    def _suggest_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Token {self._api_key}",
        }

    # ------------------------------------------------------------------
    # Response mapping — mirrors VenueAddressEnricher logic from PHP
    # ------------------------------------------------------------------

    def _map_data_to_result(self, data: dict, address_raw: str) -> GeocodingResult:
        """
        Map Dadata response to GeocodingResult.

        Mirrors backend/app/Services/VenueAddressEnricher/VenueAddressEnricher.php:
          - fias_id = settlement → city → region (NOT house/street level)
          - city_fias_id with federal city and settlement fallbacks
          - region_code for new regions without ISO
        """
        fias_id = _pick_settlement_or_city_fias_id(data)
        fias_level = _pick_fias_level(data)
        city_fias_id = _pick_city_fias_id(data)
        region_iso = _str_or_none(data.get("region_iso_code"))
        region_code = _pick_region_code(data)

        # Federal cities: if fias_level=1, city_fias_id = fias_id
        if fias_level == "1" and region_iso in FEDERAL_CITY_ISOS:
            city_fias_id = fias_id

        # Settlements (level 6): if city_fias_id still empty, use fias_id
        if city_fias_id is None and fias_level == "6" and fias_id is not None:
            city_fias_id = fias_id

        # Regions (level 1, non-federal): if city_fias_id still empty, use fias_id
        if city_fias_id is None and fias_level == "1" and fias_id is not None:
            city_fias_id = fias_id

        # If city_fias_id is still None, try to resolve from address text
        if city_fias_id is None and address_raw:
            city_fias_id = None  # would need a secondary suggest call — see note below

        return GeocodingResult(
            address_raw=address_raw,
            address_normalized=data.get("result") or data.get("value"),
            fias_id=fias_id,
            fias_level=fias_level,
            city_fias_id=city_fias_id,
            kladr_id=_pick_kladr_id(data),
            region_iso=region_iso,
            region_code=region_code,
            geo_lat=_safe_float(data.get("geo_lat")),
            geo_lon=_safe_float(data.get("geo_lon")),
            quality=data.get("quality_code"),
        )

    def _parse_party(self, data: dict) -> PartyResult:
        phones = []
        emails = []
        if data.get("phones"):
            phones = [p.get("value", "") for p in data["phones"] if p.get("value")]
        if data.get("emails"):
            emails = [e.get("value", "") for e in data["emails"] if e.get("value")]

        name_data = data.get("name", {}) or {}
        address_data = data.get("address", {}) or {}
        addr_inner = address_data.get("data", {}) or {}
        mgmt = data.get("management", {}) or {}
        opf_data = data.get("opf", {}) or {}
        state = data.get("state", {}) or {}

        return PartyResult(
            found=True,
            inn=data.get("inn"),
            ogrn=data.get("ogrn"),
            kpp=data.get("kpp"),
            name_full=name_data.get("full_with_opf"),
            name_short=name_data.get("short_with_opf"),
            opf=opf_data.get("short"),
            okved=data.get("okved"),
            director_name=mgmt.get("name"),
            director_post=mgmt.get("post"),
            address=address_data.get("value"),
            address_unrestricted=address_data.get("unrestricted_value"),
            city_fias_id=_str_or_none(addr_inner.get("city_fias_id")),
            region_fias_id=_str_or_none(addr_inner.get("region_fias_id")),
            region_iso=_str_or_none(addr_inner.get("region_iso_code")),
            geo_lat=_safe_float(addr_inner.get("geo_lat")),
            geo_lon=_safe_float(addr_inner.get("geo_lon")),
            phones=phones,
            emails=emails,
            status=state.get("status"),
            raw_data=data,
        )

    def get_metrics(self) -> dict:
        return {
            "total_calls": self._total_calls,
            "successful": self._successful,
            "failed": self._failed,
            "success_rate": self._successful / max(self._total_calls, 1),
            "mode": "clean" if self._use_clean else "suggest",
        }


# ---------------------------------------------------------------------------
# Utility functions — mirror VenueAddressEnricher private methods
# ---------------------------------------------------------------------------


def _pick_settlement_or_city_fias_id(data: dict) -> Optional[str]:
    """
    Prefer settlement_fias_id → city_fias_id → region_fias_id.
    This is what gets stored in venues.fias_id (settlement/city level, NOT house).
    """
    for key in ("settlement_fias_id", "city_fias_id", "region_fias_id"):
        val = _str_or_none(data.get(key))
        if val:
            return val
    return None


def _pick_fias_level(data: dict) -> Optional[str]:
    """Determine level of the fias_id we store: 6=settlement, 4=city, 1=region."""
    if _str_or_none(data.get("settlement_fias_id")):
        return "6"
    if _str_or_none(data.get("city_fias_id")):
        return "4"
    if _str_or_none(data.get("region_fias_id")):
        return "1"
    return None


def _pick_city_fias_id(data: dict) -> Optional[str]:
    """Extract city_fias_id from Dadata response (direct field only)."""
    return _str_or_none(data.get("city_fias_id"))


def _pick_kladr_id(data: dict) -> Optional[str]:
    """Pick most specific kladr_id available."""
    for key in (
        "house_kladr_id", "street_kladr_id", "settlement_kladr_id",
        "city_kladr_id", "region_kladr_id", "kladr_id",
    ):
        val = _str_or_none(data.get(key))
        if val:
            return val
    return None


def _pick_region_code(data: dict) -> Optional[str]:
    """
    For new regions without ISO code (LNR, DNR, Kherson, Zaporozhye),
    use region_fias_id as region_code.
    """
    region_iso = _str_or_none(data.get("region_iso_code"))
    if region_iso:
        return None  # ISO exists, no need for region_code
    return _str_or_none(data.get("region_fias_id"))


def _str_or_none(val) -> Optional[str]:
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
