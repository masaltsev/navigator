"""Verified enrichment pipeline — end-to-end URL fix and org enrichment.

Confidence-tiered single pass:
  conf >= auto_threshold (0.8)  → AUTO: full harvest, auto-import ready
  review_threshold <= conf < auto → REVIEW: verified but needs human check
  conf < review_threshold (0.5) → REJECT: skip, try social fallback

Combines all levels:
  Level 1: Search + pre-filter (aggregator/junk removal, URL normalization)
  Level 2: Site verification (lightweight crawl + LLM identity check)
  Level 3: Full harvest (multi-page crawl + OrganizationProcessor)
"""

import asyncio
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

import structlog

if TYPE_CHECKING:
    from enrichment.dadata_client import DadataClient

from processors.deepseek_client import DeepSeekClient

logger = structlog.get_logger(__name__)
from search.candidate_filter import filter_and_deduplicate, is_junk_url, normalize_to_root
from search.provider import WebSearchProvider
from search.site_verifier import SiteVerifier, VerifyResult
from search.source_discoverer import (
    DiscoveredSource,
    DiscoveryResult,
    _is_aggregator,
    discover_sources,
)
from search.url_fixer import FixResult, extract_domain_fragment, fix_broken_url


class Tier(str, Enum):
    AUTO = "auto"
    REVIEW = "review"
    REJECT = "reject"


@dataclass
class EnrichmentResult:
    """Full result of the verified enrichment pipeline for one organization."""

    org_title: str
    original_url: str
    source_id: str

    tier: Tier = Tier.REJECT

    search_result: Optional[FixResult] = None

    verified_url: Optional[str] = None
    verification: Optional[VerifyResult] = None
    all_verifications: list[VerifyResult] = field(default_factory=list)

    social_pages: list[DiscoveredSource] = field(default_factory=list)

    harvest_output: Optional[dict] = None

    additional_context: str = ""

    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.verified_url is not None

    @property
    def needs_social_only(self) -> bool:
        return not self.verified_url and bool(self.social_pages)

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dict for output files."""
        d: dict = {
            "source_id": self.source_id,
            "org_title": self.org_title,
            "original_url": self.original_url,
            "tier": self.tier.value,
            "verified": self.success,
        }

        if self.verified_url:
            d["verified_url"] = self.verified_url
        if self.verification:
            v = self.verification
            d["confidence"] = v.confidence
            d["is_main_page"] = v.is_main_page
            if v.verification:
                d["org_name_found"] = v.verification.org_name_found
                d["reasoning"] = v.verification.reasoning

        if self.social_pages:
            d["social_pages"] = [
                {"url": s.url, "kind": s.kind, "confidence": s.confidence}
                for s in self.social_pages
            ]

        if self.harvest_output:
            harvest_decision = self.harvest_output.get("ai_metadata", {}).get("decision")
            harvest_confidence = self.harvest_output.get("ai_metadata", {}).get("ai_confidence_score")
            d["harvest_decision"] = harvest_decision
            d["harvest_confidence"] = harvest_confidence
            d["harvest_title"] = self.harvest_output.get("title", "")
            d["harvest_inn"] = self.harvest_output.get("inn")
            d["harvest_works_with_elderly"] = self.harvest_output.get("ai_metadata", {}).get("works_with_elderly")

            if harvest_decision == "needs_review":
                d["tier"] = Tier.REVIEW.value
                self.tier = Tier.REVIEW

        if self.error:
            d["error"] = self.error

        return d


class EnrichmentPipeline:
    """Orchestrates the multi-level enrichment for a single organization.

    Confidence-tiered flow:
        1. Search for candidate URLs
        2. Pre-filter: remove aggregators, junk, normalize
        3. Verify top candidates via lightweight crawl + LLM
        4. Assign tier based on confidence:
           - AUTO (≥0.8): run full harvest
           - REVIEW (0.5-0.8): save for human review, no harvest
           - REJECT (<0.5): try social fallback
        5. For AUTO: run full harvest, double-check with OrgProcessor
           - If OrgProcessor says needs_review → downgrade to REVIEW
    """

    def __init__(
        self,
        search_provider: WebSearchProvider,
        deepseek_client: DeepSeekClient,
        *,
        dadata_client: Optional["DadataClient"] = None,
        max_verify_candidates: int = 5,
        auto_threshold: float = 0.8,
        review_threshold: float = 0.5,
    ):
        self._provider = search_provider
        self._llm = deepseek_client
        self._dadata = dadata_client
        self._verifier = SiteVerifier(deepseek_client)
        self._max_verify = max_verify_candidates
        self._auto_threshold = auto_threshold
        self._review_threshold = review_threshold

    async def enrich_broken_url(
        self,
        broken_url: str,
        org_title: str,
        *,
        city: str = "",
        inn: str = "",
        source_id: str = "",
        additional_context: str = "",
        source_kind: str = "org_website",
        precomputed_dadata_party: Optional[List[object]] = None,
    ) -> EnrichmentResult:
        """Fix a broken URL with full verification + tiered harvest."""
        result = EnrichmentResult(
            org_title=org_title,
            original_url=broken_url,
            source_id=source_id,
            additional_context=additional_context,
        )

        try:
            if precomputed_dadata_party:
                dadata_party = list(precomputed_dadata_party)
            else:
                dadata_party = await self._dadata_suggest(org_title, city)
            inn = inn or (dadata_party[0].inn if dadata_party else "") or ""

            fix_result = await fix_broken_url(
                broken_url,
                self._provider,
                org_title=org_title,
                city=city,
                verify_reachable=True,
                fallback_on_aggregator=True,
            )
            result.search_result = fix_result

            candidate_urls = self._extract_candidate_urls(fix_result)

            if candidate_urls:
                verified = await self._verify_candidates(
                    candidate_urls, org_title, inn, city=city,
                )
                result.all_verifications = verified
                for v in verified:
                    logger.info(
                        "enrichment_verification",
                        org=org_title[:50],
                        url=v.url[:80],
                        confidence=getattr(v, "confidence", 0.0),
                        is_match=getattr(v, "is_match", False),
                        is_main_page=getattr(v, "is_main_page", False),
                        crawl_error=v.crawl_error if getattr(v, "crawl_error", None) else None,
                    )
                if verified and all(getattr(v, "crawl_error", None) for v in verified):
                    logger.warning(
                        "enrichment_all_verifications_failed",
                        org=org_title[:50],
                        first_error=verified[0].crawl_error[:200] if verified[0].crawl_error else "",
                    )

                best = self._pick_best_verified(verified)
                if best:
                    result.verified_url = best.url
                    result.verification = best

            if result.verified_url:
                result.tier = self._assign_tier(result.verification)
            else:
                result.tier = Tier.REJECT
                social = await self._search_social(org_title, city)
                result.social_pages = social

            if result.tier == Tier.AUTO:
                result.harvest_output = await self._run_full_harvest(
                    result.verified_url, org_title, inn, source_id,
                    additional_context=additional_context,
                    source_kind=source_kind,
                )
                if result.harvest_output and dadata_party:
                    self._merge_dadata_into_harvest(result.harvest_output, dadata_party[0])

        except Exception as exc:
            logger.error("enrichment_error", org=org_title[:60], error=str(exc))
            result.error = str(exc)

        self._log_result(result)
        return result

    async def enrich_missing_source(
        self,
        org_title: str,
        *,
        city: str = "",
        inn: str = "",
        source_id: str = "",
        additional_context: str = "",
        source_kind: str = "org_website",
        precomputed_dadata_party: Optional[List[object]] = None,
    ) -> EnrichmentResult:
        """Find and verify a website for an org that has no source at all.

        Args:
            city: Region and/or city for search, Dadata suggest and LLM verification.
                Same param is used from: backend (orgs without sources, from region_iso +
                address_raw), Silver Age (org.region), SONKO (org.region_from_address),
                FPG (org.region). Ideally "Region, City" to disambiguate same-name orgs.
            additional_context: Extra text (e.g. practice descriptions from
                aggregators) prepended to raw_text before LLM classification.
            source_kind: Source kind tag for HarvestInput (e.g. "platform_silverage").
            precomputed_dadata_party: If provided, use this instead of calling Dadata
                suggest_party (avoids duplicate API calls; list of PartyResult from suggest_party).
        """
        result = EnrichmentResult(
            org_title=org_title,
            original_url="",
            source_id=source_id,
            additional_context=additional_context,
        )

        try:
            if precomputed_dadata_party:
                dadata_party = list(precomputed_dadata_party)
            else:
                dadata_party = await self._dadata_suggest(org_title, city)
            inn = inn or (dadata_party[0].inn if dadata_party else "") or ""

            discovery = await discover_sources(
                org_title,
                self._provider,
                city=city,
                verify_reachable=True,
            )

            candidate_urls = [s.url for s in discovery.official_sites if s.reachable]
            candidate_urls = filter_and_deduplicate(candidate_urls)

            logger.info(
                "enrichment_candidates",
                org=org_title[:60],
                search_provider=type(self._provider).__name__,
                query_used=discovery.query_used[:100],
                candidate_urls=candidate_urls,
                official_sites_count=len(discovery.official_sites),
                reachable_count=len(candidate_urls),
            )

            if candidate_urls:
                verified = await self._verify_candidates(
                    candidate_urls, org_title, inn, city=city,
                )
                result.all_verifications = verified

                for v in verified:
                    logger.info(
                        "enrichment_verification",
                        org=org_title[:50],
                        url=v.url[:80],
                        confidence=v.confidence,
                        is_match=v.is_match,
                        is_main_page=v.is_main_page,
                        crawl_error=v.crawl_error if getattr(v, "crawl_error", None) else None,
                    )
                if verified and all(getattr(v, "crawl_error", None) for v in verified):
                    logger.warning(
                        "enrichment_all_verifications_failed",
                        org=org_title[:50],
                        first_error=verified[0].crawl_error[:200] if verified[0].crawl_error else "",
                    )

                best = self._pick_best_verified(verified)
                if best:
                    result.verified_url = best.url
                    result.verification = best

            if result.verified_url:
                result.tier = self._assign_tier(result.verification)
            else:
                result.tier = Tier.REJECT
                social_from_search = discovery.social_pages
                verified_social = await self._verify_social(
                    social_from_search, org_title,
                )
                result.social_pages = verified_social

            if result.tier == Tier.AUTO:
                result.harvest_output = await self._run_full_harvest(
                    result.verified_url, org_title, inn, source_id,
                    additional_context=additional_context,
                    source_kind=source_kind,
                )
                if result.harvest_output and dadata_party:
                    self._merge_dadata_into_harvest(result.harvest_output, dadata_party[0])

        except Exception as exc:
            logger.error("enrichment_error", org=org_title[:60], error=str(exc))
            result.error = str(exc)

        self._log_result(result)
        return result

    def _assign_tier(self, verification: Optional[VerifyResult]) -> Tier:
        if not verification:
            return Tier.REJECT
        conf = verification.confidence
        if conf >= self._auto_threshold:
            return Tier.AUTO
        if conf >= self._review_threshold:
            return Tier.REVIEW
        return Tier.REJECT

    def _get_dadata(self) -> Optional["DadataClient"]:
        if self._dadata is not None:
            return self._dadata
        try:
            from config.settings import get_settings
            from enrichment.dadata_client import DadataClient
            s = get_settings()
            if s.dadata_api_key and s.dadata_secret_key:
                self._dadata = DadataClient(
                    api_key=s.dadata_api_key,
                    secret_key=s.dadata_secret_key,
                    use_clean=s.dadata_use_clean,
                )
                return self._dadata
        except Exception as e:
            logger.debug("dadata_not_available", reason=str(e))
        return None

    async def _dadata_suggest(
        self, org_title: str, city: str = ""
    ) -> list:
        """Call Dadata suggest_party; return list of PartyResult (empty if disabled/fail)."""
        client = self._get_dadata()
        if not client or not client.enabled:
            return []
        try:
            parties = await client.suggest_party(
                org_title.strip(),
                count=3,
                region=city.strip() or None,
            )
            if parties:
                logger.info(
                    "enrichment_dadata_suggest",
                    org=org_title[:50],
                    region=city[:40] or None,
                    inn=parties[0].inn,
                )
            return parties or []
        except Exception as e:
            logger.warning("enrichment_dadata_suggest_error", org=org_title[:40], error=str(e))
            return []

    def _merge_dadata_into_harvest(self, harvest_output: dict, party) -> None:
        """Merge Dadata party (INN, OGRN, address as venue, contacts) into harvest payload."""
        if not harvest_output or not party:
            return
        if not getattr(party, "inn", None) and not getattr(party, "address", None):
            return
        if not harvest_output.get("inn") and party.inn:
            harvest_output["inn"] = party.inn
        if not harvest_output.get("ogrn") and party.ogrn:
            harvest_output["ogrn"] = party.ogrn
        contacts = harvest_output.get("contacts") or {}
        phones = list(contacts.get("phones") or [])
        emails = list(contacts.get("emails") or [])
        for p in getattr(party, "phones", []) or []:
            if p and p not in phones:
                phones.append(p)
        for e in getattr(party, "emails", []) or []:
            if e and e not in emails:
                emails.append(e)
        harvest_output["contacts"] = {"phones": phones, "emails": emails}
        if not party.address:
            return
        try:
            geo = party.to_geocoding_result()
            venue_data = {
                "address_raw": geo.address_raw,
                "address_comment": "адрес из реестра Dadata",
            }
            if geo.fias_id:
                venue_data["fias_id"] = geo.fias_id
            if geo.geo_lat is not None and geo.geo_lon is not None:
                venue_data["geo_lat"] = geo.geo_lat
                venue_data["geo_lon"] = geo.geo_lon
            venues = list(harvest_output.get("venues") or [])
            venues.append(venue_data)
            harvest_output["venues"] = venues
            logger.info(
                "enrichment_dadata_merged",
                org=harvest_output.get("title", "")[:40],
                inn=harvest_output.get("inn"),
                venue_added=geo.address_raw[:60],
            )
        except Exception as e:
            logger.warning("enrichment_dadata_merge_venue_error", error=str(e))

    def _extract_candidate_urls(self, fix_result: FixResult) -> list[str]:
        urls = []
        for c in fix_result.candidates:
            if c.reachable and c.score >= 20.0:
                urls.append(c.url)

        urls = filter_and_deduplicate(urls)
        return urls[:self._max_verify * 2]

    async def _verify_candidates(
        self,
        urls: list[str],
        org_title: str,
        inn: str,
        *,
        city: str = "",
    ) -> list[VerifyResult]:
        return await self._verifier.verify_batch(
            urls,
            expected_org_title=org_title,
            expected_inn=inn,
            max_candidates=self._max_verify,
            region_or_city=city,
        )

    def _pick_best_verified(self, results: list[VerifyResult]) -> Optional[VerifyResult]:
        """Pick the best verified match (review_threshold minimum)."""
        matches = [
            r for r in results
            if r.is_match and r.confidence >= self._review_threshold
        ]

        main_page_matches = [r for r in matches if r.is_main_page]
        if main_page_matches:
            best = max(main_page_matches, key=lambda r: r.confidence)
            best = self._follow_suggested_url(best)
            return best

        if matches:
            best = max(matches, key=lambda r: r.confidence)
            best = self._follow_suggested_url(best)
            return best

        return None

    @staticmethod
    def _follow_suggested_url(result: VerifyResult) -> VerifyResult:
        if not result.verification or not result.verification.suggested_main_url:
            return result

        suggested = result.verification.suggested_main_url.strip()
        if not suggested or suggested == result.url:
            return result

        logger.info(
            "verify_follow_redirect",
            from_url=result.url,
            to_url=suggested,
            reasoning=result.verification.reasoning[:80],
        )
        result.url = suggested
        return result

    async def _search_social(
        self,
        org_title: str,
        city: str,
    ) -> list[DiscoveredSource]:
        social_results: list[DiscoveredSource] = []

        for platform, query_suffix in [
            ("vk_group", "вконтакте"),
            ("ok_group", "одноклассники"),
        ]:
            city_part = city or ""
            query = f"{org_title} {city_part} {query_suffix}".strip()
            try:
                results = await self._provider.search(query, num_results=5)
            except Exception:
                continue

            for r in results:
                from search.social_classifier import classify_social_url

                social = classify_social_url(r.url)
                if social.is_social and social.source_kind == platform:
                    social_results.append(DiscoveredSource(
                        url=r.url,
                        kind=social.source_kind,
                        title=r.title,
                        confidence=0.7,
                        reachable=True,
                        social_link=social,
                        reason="social_search",
                    ))

        return social_results

    async def _verify_social(
        self,
        social_pages: list[DiscoveredSource],
        org_title: str,
    ) -> list[DiscoveredSource]:
        verified: list[DiscoveredSource] = []

        for page in social_pages[:3]:
            try:
                result = await self._verifier.verify(
                    page.url, org_title,
                )
                if result.is_match:
                    page.confidence = result.confidence
                    page.reason = f"verified_{page.reason}"
                    verified.append(page)
            except Exception as exc:
                logger.warning(
                    "social_verify_error",
                    url=page.url,
                    error=str(exc),
                )

        return verified

    async def _run_full_harvest(
        self,
        url: str,
        org_title: str,
        inn: str,
        source_id: str,
        *,
        additional_context: str = "",
        source_kind: str = "org_website",
    ) -> Optional[dict]:
        """Run the full harvest pipeline on a verified URL.

        Uses harvest.run_organization_harvest (multi-page crawl, site extractor,
        additional_context). Returns org result dump for enrichment pipeline.
        """
        try:
            from harvest.run_organization_harvest import run_organization_harvest

            out = await run_organization_harvest(
                url,
                source_id=source_id or "enrichment",
                source_item_id=url,
                existing_entity_id=None,
                multi_page=True,
                enrich_geo=True,
                additional_context=additional_context,
                source_kind=source_kind,
                try_site_extractor=True,
                deepseek_client=self._llm,
            )

            if not out["success"]:
                logger.warning("harvest_crawl_failed", url=url, error=out.get("error"))
                return None

            return {
                "payload": out["payload"],
                "crawl_meta": out.get("crawl_meta"),
                "geo_results": out.get("geo_results"),
                "llm_metrics": out.get("llm_metrics"),
            }

        except Exception as exc:
            logger.error("harvest_error", url=url, error=str(exc))
            return {"error": str(exc)}

    def _log_result(self, result: EnrichmentResult) -> None:
        logger.info(
            "enrichment_result",
            org=result.org_title[:60],
            original_url=result.original_url[:60] if result.original_url else "",
            verified_url=result.verified_url or "",
            tier=result.tier.value,
            social_pages=len(result.social_pages),
            verifications=len(result.all_verifications),
            success=result.success,
            error=result.error,
        )


