"""Fix broken org_website URLs by searching for correct ones.

Scenario A from the enrichment plan: an organisation has a source with
kind=org_website, but the URL is invalid (truncated domain, missing TLD,
DNS failure, site migrated). This module extracts a domain fragment,
searches for the likely correct URL, and ranks candidates.

Fallback: if fragment-based search fails or returns only aggregators,
the fixer retries with a name+city search via discover_sources logic.
"""

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import structlog

from enrichment.url_validator import validate_url
from search.provider import SearchResult, WebSearchProvider
from search.source_discoverer import _is_aggregator

logger = structlog.get_logger(__name__)

_JUNK_TLDS = {"ru", "com", "org", "net", "рф", "gov", "www", "http", "https"}


@dataclass
class FixCandidate:
    """A candidate URL that may replace a broken one."""

    url: str
    score: float
    reachable: bool
    title: str
    reason: str


@dataclass
class FixResult:
    """Result of attempting to fix one broken URL."""

    original_url: str
    fragment: str
    candidates: list[FixCandidate]
    best: FixCandidate | None
    search_results_count: int

    @property
    def fixed(self) -> bool:
        return self.best is not None and self.best.reachable


def extract_domain_fragment(url: str) -> str:
    """Extract a searchable fragment from a broken URL.

    Examples:
        "https://mikh-kcson.ryazan."  -> "mikh-kcson ryazan"
        "kcson23.uszn032.ru"          -> "kcson23 uszn032"
        "https://fond-tut.ru"         -> "fond-tut"
        "http://www.kcson-vologda.gov35.ru" -> "kcson-vologda gov35"
    """
    cleaned = url.strip()
    cleaned = re.sub(r'^https?://', '', cleaned)
    cleaned = re.sub(r'^www\.', '', cleaned)
    cleaned = re.sub(r'/.*$', '', cleaned)
    cleaned = cleaned.rstrip('.')

    parts = cleaned.split('.')
    meaningful = [p for p in parts if p and p.lower() not in _JUNK_TLDS]

    if not meaningful and parts:
        meaningful = [p for p in parts if p]

    fragment = ' '.join(meaningful)
    return fragment


def _score_candidate(
    result: SearchResult,
    fragment: str,
    org_title: str = "",
) -> tuple[float, str]:
    """Score a search result as a candidate replacement URL.

    Returns (score, reason).
    """
    score = 0.0
    reasons: list[str] = []
    url_lower = result.url.lower()
    parsed = urlparse(result.url)
    hostname = (parsed.hostname or "").lower()

    fragment_parts = fragment.lower().split()
    matched_parts = sum(1 for p in fragment_parts if p in hostname)
    if fragment_parts:
        match_ratio = matched_parts / len(fragment_parts)
        if match_ratio >= 0.8:
            score += 50
            reasons.append(f"domain_match_{match_ratio:.0%}")
        elif match_ratio >= 0.5:
            score += 25
            reasons.append(f"partial_domain_{match_ratio:.0%}")

    if org_title:
        title_words = {w.lower() for w in org_title.split() if len(w) > 3}
        snippet_text = f"{result.title} {result.snippet}".lower()
        title_matches = sum(1 for w in title_words if w in snippet_text)
        if title_words and title_matches / len(title_words) >= 0.3:
            score += 30
            reasons.append(f"title_match_{title_matches}/{len(title_words)}")

    if url_lower.startswith("https://"):
        score += 10
        reasons.append("https")

    if hostname.endswith((".ru", ".рф", ".gov.ru")):
        score += 10
        reasons.append("ru_domain")

    social_domains = ("vk.com", "ok.ru", "t.me", "facebook.com", "instagram.com")
    if any(d in hostname for d in social_domains):
        score -= 20
        reasons.append("social_media_penalty")

    aggregator_domains = ("2gis.ru", "yandex.ru/maps", "google.com/maps", "zoon.ru")
    if any(d in url_lower for d in aggregator_domains):
        score -= 15
        reasons.append("aggregator_penalty")

    if result.position <= 3:
        score += 5
        reasons.append(f"top_{result.position}")

    return max(score, 0.0), "; ".join(reasons)


async def check_url_reachable(url: str, timeout: float = 10.0) -> bool:
    """HEAD request to verify URL is reachable (2xx or 3xx)."""
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=False,
        ) as client:
            resp = await client.head(url)
            return resp.status_code < 400
    except Exception:
        return False


async def fix_broken_url(
    broken_url: str,
    provider: WebSearchProvider,
    org_title: str = "",
    city: str = "",
    *,
    verify_reachable: bool = True,
    min_score: float = 20.0,
    fallback_on_aggregator: bool = True,
) -> FixResult:
    """Attempt to find the correct URL for a broken org_website.

    Steps:
      1. Extract domain fragment from broken URL
      2. Search for the fragment (+ org_title if available)
      3. Score and rank candidates
      4. Optionally verify top candidates are reachable (HEAD request)
      5. If best candidate is an aggregator or not found, and org_title is
         available, retry with a name+city search (fallback)
      6. Return the best candidate above min_score threshold
    """
    fragment = extract_domain_fragment(broken_url)
    if not fragment:
        logger.warning("url_fixer_no_fragment", url=broken_url)
        return FixResult(
            original_url=broken_url,
            fragment="",
            candidates=[],
            best=None,
            search_results_count=0,
        )

    if org_title:
        query = f'{org_title} "{fragment}" сайт'
        results = await provider.search(query, num_results=10)
    else:
        results = await provider.search_by_domain_fragment(fragment)

    best, candidates, total_results = await _pick_best(
        results, fragment, org_title, verify_reachable, min_score
    )

    needs_fallback = (
        fallback_on_aggregator
        and org_title
        and (best is None or _is_aggregator(best.url))
    )
    if needs_fallback:
        reason = "aggregator" if best and _is_aggregator(best.url) else "no_match"
        logger.info("url_fixer_fallback", url=broken_url, reason=reason)

        city_part = city if city else ""
        fallback_query = f"{org_title} {city_part} официальный сайт".strip()
        fb_results = await provider.search(fallback_query, num_results=10)
        total_results += len(fb_results)

        fb_best, fb_candidates, _ = await _pick_best(
            fb_results, fragment, org_title, verify_reachable, min_score
        )
        candidates.extend(fb_candidates)

        if fb_best and not _is_aggregator(fb_best.url):
            best = fb_best

    logger.info(
        "url_fixer_result",
        url=broken_url,
        fragment=fragment,
        candidates=len(candidates),
        best_url=best.url if best else None,
        best_score=best.score if best else None,
        fallback=needs_fallback,
    )

    return FixResult(
        original_url=broken_url,
        fragment=fragment,
        candidates=candidates,
        best=best,
        search_results_count=total_results,
    )


async def _pick_best(
    results: list[SearchResult],
    fragment: str,
    org_title: str,
    verify_reachable: bool,
    min_score: float,
) -> tuple[FixCandidate | None, list[FixCandidate], int]:
    """Score results, check reachability, return (best, all_candidates, count)."""
    candidates: list[FixCandidate] = []
    for r in results:
        is_valid, _ = validate_url(r.url)
        if not is_valid:
            continue

        score, reason = _score_candidate(r, fragment, org_title)
        candidates.append(FixCandidate(
            url=r.url,
            score=score,
            reachable=False,
            title=r.title,
            reason=reason,
        ))

    candidates.sort(key=lambda c: c.score, reverse=True)

    if verify_reachable:
        for c in candidates[:3]:
            c.reachable = await check_url_reachable(c.url)

    best = None
    for c in candidates:
        if c.score >= min_score and (not verify_reachable or c.reachable):
            best = c
            break

    return best, candidates, len(results)
