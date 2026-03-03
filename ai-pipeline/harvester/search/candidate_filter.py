"""Pre-filter and normalize candidate URLs before verification.

Level 1 of the enrichment pipeline — no network calls, instant.
Filters out aggregators, normalizes URLs to root, deduplicates.
"""

import re
from urllib.parse import urlparse, urlunparse

from search.source_discoverer import _is_aggregator

_JUNK_URL_PATTERNS = [
    re.compile(r"yandex\.ru/images/"),
    re.compile(r"yandex\.ru/search/"),
    re.compile(r"google\.\w+/search"),
    re.compile(r"google\.\w+/maps"),
    re.compile(r"webcache\.googleusercontent\.com"),
]


def is_junk_url(url: str) -> bool:
    """Check if URL is a search engine result page, image search, etc."""
    return any(p.search(url) for p in _JUNK_URL_PATTERNS)


def normalize_to_root(url: str) -> str:
    """Normalize URL to the root of its likely site section.

    Examples:
        https://soc13.ru/pi_purkaevo/news        → https://soc13.ru/pi_purkaevo/
        https://tomarovinternat.ru/about/         → https://tomarovinternat.ru/
        https://chita-pndi.zabguso.ru/1344-2/     → https://chita-pndi.zabguso.ru/
        https://kcsonviaz.mszn27.ru/about         → https://kcsonviaz.mszn27.ru/

    Heuristic: if the hostname has a distinctive subdomain (not www),
    keep just the root. If the path has 1 segment that looks like a
    site section slug (letters/hyphens, no file extension), keep it.
    """
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    parts = hostname.split(".")
    has_subdomain = len(parts) > 2 and parts[0] not in ("www", "m")

    path = parsed.path.rstrip("/")
    segments = [s for s in path.split("/") if s]

    if not segments or has_subdomain:
        return urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))

    first_seg = segments[0]
    looks_like_slug = (
        re.match(r"^[a-zA-Z0-9_-]+$", first_seg)
        and "." not in first_seg
        and len(first_seg) > 2
    )

    if has_subdomain and looks_like_slug:
        return urlunparse((parsed.scheme, parsed.netloc, f"/{first_seg}/", "", "", ""))

    return urlunparse((parsed.scheme, parsed.netloc, "/", "", "", ""))


def filter_and_deduplicate(
    urls: list[str],
    *,
    keep_social: bool = False,
) -> list[str]:
    """Filter out junk/aggregator URLs, normalize to root, deduplicate.

    Returns deduplicated root URLs in order of first appearance.
    """
    seen_roots: set[str] = set()
    result: list[str] = []

    _social_domains = {"vk.com", "ok.ru", "t.me"}

    for url in urls:
        if is_junk_url(url):
            continue
        if _is_aggregator(url):
            continue

        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()

        is_social = any(hostname.endswith(d) or hostname == d for d in _social_domains)
        if is_social and not keep_social:
            continue

        root = normalize_to_root(url)
        if root not in seen_roots:
            seen_roots.add(root)
            result.append(root)

    return result
