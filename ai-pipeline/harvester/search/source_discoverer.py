"""Discover websites and social pages for organisations without sources.

Scenario B from the enrichment plan: an organisation has no source with
kind=org_website. This module searches for the organisation's website
and classifies results into official sites vs social media pages.
"""

from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
import structlog

from enrichment.url_validator import validate_url
from search.provider import SearchResult, WebSearchProvider
from search.social_classifier import SocialLink, classify_social_url

logger = structlog.get_logger(__name__)

# Domains we treat as aggregators: company/org directories, registries, SEO-heavy
# catalogues. Excluded from official_sites so we don't crawl or spend LLM tokens on them.
# Can be extended with domains LLM has identified as aggregators in runs.
_AGGREGATOR_DOMAINS = frozenset({
    # Maps & directories
    "2gis.ru", "zoon.ru", "yell.ru", "cataloxy.ru", "orgpage.ru",
    "spr.ru", "google.com", "google.ru", "maps.yandex.ru",
    # Company/org registries and data providers
    "rusprofile.ru", "list-org.com", "egrul.nalog.ru",
    "checko.ru", "checkos.ru", "sbis.ru",
    "kontur.ru",           # focus.kontur.ru, spark.kontur.ru, etc.
    "companies.rbc.ru",   # RBC company directory
    "audit-it.ru",
    "spark-interfax.ru",
    "fedresurs.ru",
    # Medical/org directories (SEO, not org sites)
    "prodoctorov.ru", "doctu.ru", "napriem.info",
    # Volunteer/company directories
    "dobro.ru", "companium.ru", "saby.ru", "b2b.house",
    "gkbru.ru",           # regional directory
    # Government aggregators
    "bus.gov.ru",
    # Reference / encyclopedias
    "wikipedia.org", "wikiwand.com",
    # Yandex services (not org sites)
    "yandex.ru",
    # Review / rating aggregators
    "allpans.ru", "fond60.ru", "star-pro.ru", "all-pansionat.ru",
    "vozrast-portal.ru", "edu2you.ru", "meddoclab.ru",
    "vsekcson.ru",
    # Our own catalog (not an org site)
    "navigator.vnuki.fund",
})

_OFFICIAL_TLDS = frozenset({".ru", ".рф", ".su", ".gov.ru", ".com", ".org", ".net"})


@dataclass
class DiscoveredSource:
    """A website or social page found for an organisation."""

    url: str
    kind: str  # org_website | vk_group | ok_group | tg_channel
    title: str
    confidence: float
    reachable: bool
    social_link: SocialLink | None = None
    reason: str = ""


@dataclass
class DiscoveryResult:
    """Full result of source discovery for one organisation."""

    org_title: str
    city: str
    query_used: str
    search_results_count: int
    official_sites: list[DiscoveredSource] = field(default_factory=list)
    social_pages: list[DiscoveredSource] = field(default_factory=list)
    skipped_aggregators: int = 0

    @property
    def found_anything(self) -> bool:
        return bool(self.official_sites or self.social_pages)

    @property
    def best_official(self) -> DiscoveredSource | None:
        reachable = [s for s in self.official_sites if s.reachable]
        return reachable[0] if reachable else (self.official_sites[0] if self.official_sites else None)


def _is_aggregator(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname == d or hostname.endswith(f".{d}") for d in _AGGREGATOR_DOMAINS)


def _score_official_site(
    result: SearchResult,
    org_title: str,
) -> float:
    """Score how likely a search result is the organisation's official website."""
    score = 0.0
    parsed = urlparse(result.url)
    hostname = (parsed.hostname or "").lower()

    if any(hostname.endswith(tld) for tld in _OFFICIAL_TLDS):
        score += 10

    if hostname.endswith(".gov.ru"):
        score += 15

    title_words = {w.lower() for w in org_title.split() if len(w) > 3}
    snippet_text = f"{result.title} {result.snippet}".lower()
    if title_words:
        matches = sum(1 for w in title_words if w in snippet_text)
        score += 30 * (matches / len(title_words))

    hostname_clean = hostname.replace("www.", "")
    org_key_words = {w.lower() for w in org_title.split() if len(w) > 4}
    for w in org_key_words:
        if w in hostname_clean:
            score += 20
            break

    if result.url.startswith("https://"):
        score += 5

    if result.position <= 3:
        score += 10

    return round(score, 1)


async def _check_reachable(url: str, timeout: float = 10.0) -> bool:
    try:
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, verify=False
        ) as client:
            resp = await client.head(url)
            return resp.status_code < 400
    except Exception:
        return False


async def discover_sources(
    org_title: str,
    provider: WebSearchProvider,
    city: str = "",
    *,
    num_results: int = 18,
    verify_reachable: bool = True,
    min_official_score: float = 15.0,
) -> DiscoveryResult:
    """Search for the organisation's website and social pages.

    Aggregator domains (kontur.ru, audit-it.ru, prodoctorov.ru, etc.) are skipped
    so we take the top of the search *without* aggregators and avoid wasting
    crawl/LLM on them.

    city: region and/or city (e.g. "Костромская область, Кострома"). For the search query
        text we prefer city when present (more specific); for Yandex lr we use region only.

    Steps:
      1. Build query: "<org_title>" <query_geo> официальный сайт (query_geo = city when "region, city")
      2. Search via provider with region_id from region (Yandex lr)
      3. For each result: skip aggregators; classify as official / social
      4. Score official candidates
      5. Verify reachability of top candidates
    """
    from search.yandex_xml_provider import region_name_to_yandex_lr, split_geo_for_search

    query_geo, lr_geo = split_geo_for_search(city)
    region_id = None
    if lr_geo:
        try:
            region_id = region_name_to_yandex_lr(lr_geo)
        except Exception:
            pass
    results = await provider.search_for_site(
        org_title, query_geo, num_results=num_results, region_id=region_id
    )

    query_parts = [f'"{org_title}"']
    if query_geo:
        query_parts.append(query_geo)
    query_parts.append("официальный сайт")
    query_used = " ".join(query_parts)

    discovery = DiscoveryResult(
        org_title=org_title,
        city=city,
        query_used=query_used,
        search_results_count=len(results),
    )

    for r in results:
        is_valid, _ = validate_url(r.url)
        if not is_valid:
            continue

        if _is_aggregator(r.url):
            discovery.skipped_aggregators += 1
            continue

        social = classify_social_url(r.url)
        if social.is_social:
            discovery.social_pages.append(DiscoveredSource(
                url=r.url,
                kind=social.source_kind,
                title=r.title,
                confidence=0.7,
                reachable=True,
                social_link=social,
                reason="social_from_search",
            ))
            continue

        score = _score_official_site(r, org_title)
        if score >= min_official_score:
            discovery.official_sites.append(DiscoveredSource(
                url=r.url,
                kind="org_website",
                title=r.title,
                confidence=min(score / 100, 1.0),
                reachable=False,
                reason=f"score={score}",
            ))

    discovery.official_sites.sort(key=lambda s: s.confidence, reverse=True)

    # Check reachability for top 5 so we have more candidates for verification (order may vary by provider).
    if verify_reachable:
        for s in discovery.official_sites[:5]:
            s.reachable = await _check_reachable(s.url)

    logger.info(
        "source_discovery",
        org=org_title[:60],
        city=city,
        query_used=query_used[:100],
        official=len(discovery.official_sites),
        social=len(discovery.social_pages),
        skipped=discovery.skipped_aggregators,
    )
    # Log candidate URLs for debugging: search may return wrong order or DDG vs Yandex differ.
    if discovery.official_sites:
        candidates_log = [
            {"url": s.url, "reachable": s.reachable, "score_reason": s.reason}
            for s in discovery.official_sites[:8]
        ]
        logger.info(
            "source_discovery_candidates",
            org=org_title[:50],
            candidates=candidates_log,
        )

    return discovery
