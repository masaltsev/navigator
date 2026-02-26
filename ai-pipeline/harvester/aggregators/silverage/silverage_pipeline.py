"""End-to-end Silver Age pipeline.

Flow:
  1. Scrape practice list (paginated, ~1051 practices)
  2. For each practice: scrape detail page -> extract org info
  3. Group practices by org name -> deduplicate
  4. For each unique org:
     a. Dadata suggest_party(name, region) -> INN
     b. Lookup in Core by INN (and source_reference)
     c. If matched: list_sources(organizer_id, kind=org_website). If no source ->
        search for website and create source. If has source and last_crawled_at not set ->
        crawl and set last_crawled_at. In any case merge practice context into description.
     d. If new: search for website, harvest, import_organizer + create source; merge context.
  5. Scrape events list -> create event records
  6. Report

Key differences from FPG/SONKO:
  - Web scraping (not XLSX)
  - No INN in source data -> Dadata suggest_party first, then match by INN
  - All content is elderly-relevant (no filtering needed)
  - Events are also imported (with page_url stored)
"""

import asyncio
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from aggregators.silverage.models import (
    SilverAgeEvent,
    SilverAgeOrganization,
    SilverAgePractice,
)
from aggregators.silverage.scraper import SilverAgeScraper
from config.settings import get_settings
from core_client.api import NavigatorCoreClient
from enrichment.dadata_client import DadataClient
from event_ingestion import run_event_ingestion_pipeline, silverage_event_to_raw
from processors.deepseek_client import DeepSeekClient

logger = structlog.get_logger(__name__)
settings = get_settings()


@dataclass
class OrgResult:
    name: str
    region: str
    practice_count: int
    action: str = ""
    core_organizer_id: Optional[str] = None
    discovered_website: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "region": self.region,
            "practice_count": self.practice_count,
            "action": self.action,
            "core_organizer_id": self.core_organizer_id,
            "discovered_website": self.discovered_website,
            "error": self.error,
        }


@dataclass
class EventResult:
    title: str
    date_text: str
    location: str
    page_url: str
    action: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "date_text": self.date_text,
            "location": self.location,
            "page_url": self.page_url,
            "action": self.action,
            "error": self.error,
        }


@dataclass
class PipelineReport:
    total_practices: int = 0
    unique_organizations: int = 0
    total_events: int = 0
    org_results: list[OrgResult] = field(default_factory=list)
    event_results: list[EventResult] = field(default_factory=list)

    @property
    def orgs_created(self) -> int:
        return sum(1 for r in self.org_results if r.action in ("created", "created_minimal"))

    @property
    def orgs_matched(self) -> int:
        return sum(1 for r in self.org_results if r.action == "matched")

    @property
    def orgs_errors(self) -> int:
        return sum(1 for r in self.org_results if r.action == "error")

    def summary(self) -> str:
        lines = [
            "=== Silver Age Pipeline Report ===",
            f"Practices scraped:        {self.total_practices}",
            f"Unique organizations:     {self.unique_organizations}",
            f"  Created new:            {self.orgs_created}",
            f"  Matched existing:       {self.orgs_matched}",
            f"  Errors:                 {self.orgs_errors}",
            f"Events scraped:           {self.total_events}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "total_practices": self.total_practices,
            "unique_organizations": self.unique_organizations,
            "total_events": self.total_events,
            "org_results": [r.to_dict() for r in self.org_results],
            "event_results": [r.to_dict() for r in self.event_results],
        }


def group_practices_by_org(
    practices: list[SilverAgePractice],
) -> list[SilverAgeOrganization]:
    """Group practices by organization name."""
    org_map: dict[str, list[SilverAgePractice]] = defaultdict(list)

    for p in practices:
        key = p.org_name.strip().lower() if p.org_name else p.title.strip().lower()
        org_map[key].append(p)

    organizations: list[SilverAgeOrganization] = []
    for _key, org_practices in org_map.items():
        first = org_practices[0]
        org = SilverAgeOrganization(
            name=first.org_name or first.title,
            description=first.org_description,
            region=first.region,
            email=first.org_email,
            phone=first.org_phone,
            website=first.org_website,
            vk_url=first.org_vk,
            social_links=first.org_social_links,
            practices=org_practices,
        )
        organizations.append(org)

    organizations.sort(key=lambda o: o.practice_count, reverse=True)
    return organizations


class SilverAgePipeline:
    def __init__(
        self,
        core_client: Optional[NavigatorCoreClient] = None,
        dadata_client: Optional[DadataClient] = None,
        search_provider: Optional[object] = None,
        scrape_delay: float = 1.5,
        process_delay: float = 1.0,
        cache_dir: Optional[str] = None,
    ):
        self._core = core_client or NavigatorCoreClient(
            base_url=settings.core_api_url,
            api_token=settings.core_api_token,
        )
        self._dadata = dadata_client or DadataClient(
            api_key=settings.dadata_api_key,
            secret_key=settings.dadata_secret_key,
        )
        self._search_provider = search_provider
        self._scrape_delay = scrape_delay
        self._process_delay = process_delay
        self._cache_dir = cache_dir

    async def run(
        self,
        max_pages: Optional[int] = None,
        max_practices: Optional[int] = None,
        limit_orgs: Optional[int] = None,
        dry_run: bool = False,
        scrape_events: bool = True,
        output_path: Optional[str] = None,
    ) -> PipelineReport:
        report = PipelineReport()

        logger.info("Silver Age pipeline starting", max_pages=max_pages, dry_run=dry_run)

        scraper = SilverAgeScraper(
            delay=self._scrape_delay,
            cache_dir=self._cache_dir,
        )

        practices = await scraper.scrape_all_practices(
            max_pages=max_pages,
            max_practices=max_practices,
        )
        report.total_practices = len(practices)

        organizations = group_practices_by_org(practices)
        report.unique_organizations = len(organizations)

        logger.info(
            "Silver Age practices grouped",
            practices=len(practices),
            orgs=len(organizations),
        )

        if limit_orgs:
            organizations = organizations[:limit_orgs]

        for i, org in enumerate(organizations):
            logger.info(
                "Processing Silver Age org",
                progress=f"{i+1}/{len(organizations)}",
                name=org.name[:60],
                practices=org.practice_count,
            )
            result = await self._process_organization(org, dry_run=dry_run)
            report.org_results.append(result)

            if i < len(organizations) - 1 and self._process_delay > 0:
                await asyncio.sleep(self._process_delay)

        if scrape_events:
            events = await scraper.scrape_all_events()
            report.total_events = len(events)

            for event in events:
                event_result = await self._process_event(event, dry_run=dry_run)
                report.event_results.append(event_result)

        logger.info("Silver Age pipeline complete\n" + report.summary())

        if output_path:
            self._save_report(report, output_path)

        return report

    async def scrape_only(
        self,
        max_pages: Optional[int] = None,
        max_practices: Optional[int] = None,
    ) -> tuple[list[SilverAgePractice], list[SilverAgeOrganization]]:
        """Scrape without processing -- for analysis."""
        scraper = SilverAgeScraper(
            delay=self._scrape_delay,
            cache_dir=self._cache_dir,
        )
        practices = await scraper.scrape_all_practices(
            max_pages=max_pages,
            max_practices=max_practices,
        )
        organizations = group_practices_by_org(practices)
        return practices, organizations

    @staticmethod
    def _build_practice_context(org: SilverAgeOrganization) -> str:
        """Build additional context from Silver Age practices for LLM input.

        Aggregates practice titles, descriptions and categories so the LLM
        can use them for classification alongside the website content.
        """
        parts = [
            f"[Контекст из агрегатора silveragemap.ru — Коалиция «Забота рядом»]",
            f"Организация: {org.name}",
            f"Регион: {org.region}",
        ]

        if org.all_categories:
            parts.append(f"Категории практик: {', '.join(sorted(org.all_categories))}")

        parts.append(f"Количество практик: {org.practice_count}")

        for i, p in enumerate(org.practices[:5], 1):
            parts.append(f"\nПрактика {i}: «{p.title}»")
            desc = p.full_description or p.short_description
            if desc:
                parts.append(f"Описание: {desc[:500]}")
            if p.categories:
                parts.append(f"Категории: {', '.join(p.categories)}")

        parts.append(
            "\nВсе практики на сайте silveragemap.ru относятся к работе "
            "с людьми старшего возраста."
        )
        return "\n".join(parts)

    @staticmethod
    def _source_is_due(source: dict) -> bool:
        """True if source has never been crawled (last_crawled_at not set)."""
        return not source.get("last_crawled_at")

    async def _process_organization(
        self,
        org: SilverAgeOrganization,
        dry_run: bool = False,
    ) -> OrgResult:
        result = OrgResult(
            name=org.name,
            region=org.region,
            practice_count=org.practice_count,
        )

        try:
            if dry_run:
                result.action = "dry_run"
                result.discovered_website = org.website
                return result

            inn = ""
            party = await self._dadata.suggest_party(org.name, region=org.region)
            if party:
                inn = party[0].inn or ""
                logger.info(
                    "Dadata suggest_party match",
                    org=org.name[:60], inn=inn,
                )

            if inn:
                existing = await self._core.lookup_organization(
                    inn=inn, source_reference=org.source_reference,
                )
            else:
                existing = await self._core.lookup_organization(
                    source_reference=org.source_reference,
                )

            context = self._build_practice_context(org)

            if existing:
                result.action = "matched"
                result.core_organizer_id = existing.get("organizer_id")
                organizer_id = existing.get("organizer_id")
                sources = await self._core.list_sources(organizer_id, kind="org_website")
                org_website_source = next(
                    (s for s in sources if (s or {}).get("kind") == "org_website"),
                    None,
                )

                if not org_website_source:
                    # No org_website source — run search-for-source strategy.
                    pipeline = self._get_enrichment_pipeline()
                    if pipeline:
                        if (org.website or "").strip():
                            enrichment = await pipeline.enrich_broken_url(
                                (org.website or "").strip(),
                                org.name,
                                city=org.region,
                                inn=inn,
                                source_id=org.source_reference,
                                additional_context=context,
                                source_kind="platform_silverage",
                                precomputed_dadata_party=party,
                            )
                        else:
                            enrichment = await pipeline.enrich_missing_source(
                                org_title=org.name,
                                city=org.region,
                                inn=inn,
                                source_id=org.source_reference,
                                additional_context=context,
                                source_kind="platform_silverage",
                                precomputed_dadata_party=party,
                            )
                        if enrichment.success and enrichment.verified_url:
                            await self._core.create_source(
                                organizer_id, enrichment.verified_url, kind="org_website",
                            )
                            result.discovered_website = enrichment.verified_url
                else:
                    # Has org_website source: crawl only if due date not set.
                    if self._source_is_due(org_website_source):
                        await self._crawl_source_and_mark(
                            org_website_source, org, context, inn=inn, dadata_party=party
                        )
                    # else: leave as is, scheduler will pick when due

                # In any case for matched org: merge practice context into description.
                await self._update_matched_org(existing, org, context)
                return result

            # New organization: search for source, create org + source, description with context.
            pipeline = self._get_enrichment_pipeline()
            if pipeline:
                if (org.website or "").strip():
                    enrichment = await pipeline.enrich_broken_url(
                        (org.website or "").strip(),
                        org.name,
                        city=org.region,
                        inn=inn,
                        source_id=org.source_reference,
                        additional_context=context,
                        source_kind="platform_silverage",
                        precomputed_dadata_party=party,
                    )
                else:
                    enrichment = await pipeline.enrich_missing_source(
                        org_title=org.name,
                        city=org.region,
                        inn=inn,
                        source_id=org.source_reference,
                        additional_context=context,
                        source_kind="platform_silverage",
                        precomputed_dadata_party=party,
                    )

                if enrichment.success and enrichment.harvest_output:
                    payload = enrichment.harvest_output
                    payload["source_reference"] = org.source_reference
                    if inn:
                        payload["inn"] = inn
                    self._merge_practice_context_into_description(payload, org, context)
                    import_result = await self._core.import_organizer(payload)
                    result.action = "created"
                    result.discovered_website = enrichment.verified_url
                    result.core_organizer_id = import_result.get("organizer_id")
                    if result.core_organizer_id and enrichment.verified_url:
                        await self._create_source_record(
                            result.core_organizer_id, enrichment.verified_url,
                        )
                    return result

            import_result = await self._create_minimal_org(org, inn=inn, dadata_party=party)
            result.action = "created_minimal"
            result.core_organizer_id = import_result.get("organizer_id")
            if result.core_organizer_id:
                await self._update_matched_org(
                    {
                        "organizer_id": result.core_organizer_id,
                        "title": org.name,
                        "description": "",
                        "ai_metadata": {},
                    },
                    org, context,
                )

        except Exception as e:
            result.action = "error"
            result.error = str(e)
            logger.error("Error processing Silver Age org", name=org.name[:60], error=str(e))

        return result

    def _get_enrichment_pipeline(self):
        """Lazily initialize EnrichmentPipeline."""
        if not hasattr(self, "_enrichment_pipeline"):
            try:
                from processors.deepseek_client import DeepSeekClient
                from search.enrichment_pipeline import EnrichmentPipeline

                provider = self._search_provider or self._init_search_provider()
                if not provider:
                    self._enrichment_pipeline = None
                    return None

                llm = DeepSeekClient(
                    api_key=settings.deepseek_api_key,
                    model=settings.deepseek_model_name,
                )
                self._enrichment_pipeline = EnrichmentPipeline(provider, llm)
            except Exception:
                self._enrichment_pipeline = None
        return self._enrichment_pipeline

    async def _update_matched_org(
        self,
        existing: dict,
        org: SilverAgeOrganization,
        context: str,
    ) -> None:
        """Update an existing matched org with practice context."""
        organizer_id = existing.get("organizer_id")
        if not organizer_id:
            return

        practice_titles = ", ".join(f"«{p.title}»" for p in org.practices[:5])
        payload = {
            "source_reference": org.source_reference,
            "entity_type": "Organization",
            "title": existing.get("title", org.name),
            "description": (
                f"{existing.get('description', '')}\n\n"
                f"Дополнительно из silveragemap.ru: {org.best_description[:300]}. "
                f"Практики: {practice_titles}."
            ).strip(),
            "ai_metadata": {
                "decision": existing.get("ai_metadata", {}).get("decision", "needs_review"),
                "ai_confidence_score": existing.get("ai_metadata", {}).get("ai_confidence_score", 0.6),
                "works_with_elderly": True,
                "ai_source_trace": existing.get("ai_metadata", {}).get("ai_source_trace", []) + [
                    {
                        "source_kind": "platform_silverage",
                        "source_url": org.practices[0].page_url if org.practices else "https://silveragemap.ru",
                        "fields_extracted": ["practice_titles", "practice_descriptions", "categories"],
                    }
                ],
            },
        }

        try:
            await self._core.import_organizer(payload)
            logger.info(
                "Matched org updated with Silver Age context",
                organizer_id=organizer_id,
                practices=org.practice_count,
            )
        except Exception as exc:
            logger.warning("Failed to update matched org", error=str(exc))

    def _merge_practice_context_into_description(
        self, payload: dict, org: SilverAgeOrganization, context: str
    ) -> None:
        """Append practice context to payload['description'] (in-place)."""
        existing = (payload.get("description") or "").strip()
        suffix = (
            f"\n\nДополнительно из silveragemap.ru: {org.best_description[:300]}. "
            f"Практики: {', '.join(f'«{p.title}»' for p in org.practices[:5])}."
        )
        payload["description"] = (existing + suffix).strip() if existing else suffix.strip()

    def _merge_party_into_payload(self, payload: dict, party: object) -> None:
        """Merge Dadata party (INN, OGRN, contacts, venue with geo) into harvest payload in-place."""
        if not party:
            return
        if not getattr(party, "inn", None) and not getattr(party, "address", None):
            return
        if not payload.get("inn") and getattr(party, "inn", None):
            payload["inn"] = party.inn
        if not payload.get("ogrn") and getattr(party, "ogrn", None):
            payload["ogrn"] = party.ogrn
        contacts = payload.get("contacts") or {}
        phones = list(contacts.get("phones") or [])
        emails = list(contacts.get("emails") or [])
        for p in getattr(party, "phones", []) or []:
            if p and p not in phones:
                phones.append(p)
        for e in getattr(party, "emails", []) or []:
            if e and e not in emails:
                emails.append(e)
        payload["contacts"] = {"phones": phones, "emails": emails}
        if not getattr(party, "address", None):
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
            venues = list(payload.get("venues") or [])
            venues.append(venue_data)
            payload["venues"] = venues
        except Exception:
            pass

    async def _crawl_source_and_mark(
        self,
        source: dict,
        org: SilverAgeOrganization,
        context: str,
        *,
        inn: str = "",
        dadata_party: Optional[list] = None,
    ) -> None:
        """Run harvest for source base_url, push payload to Core (with Dadata merge), set last_crawled_at."""
        base_url = (source or {}).get("base_url")
        source_id = (source or {}).get("id")
        if not base_url or not source_id:
            return
        try:
            from harvest.run_organization_harvest import run_organization_harvest
            from processors.deepseek_client import DeepSeekClient

            llm = DeepSeekClient(
                api_key=settings.deepseek_api_key,
                model=settings.deepseek_model_name,
            )
            out = await run_organization_harvest(
                base_url,
                source_id=source_id,
                source_item_id=base_url,
                existing_entity_id=source.get("organizer_id"),
                multi_page=True,
                enrich_geo=True,
                additional_context=context,
                source_kind="org_website",
                try_site_extractor=True,
                deepseek_client=llm,
            )
            if out.get("success") and out.get("payload"):
                payload = out["payload"]
                payload["source_reference"] = org.source_reference
                if inn:
                    payload["inn"] = inn
                if dadata_party and len(dadata_party) > 0:
                    self._merge_party_into_payload(payload, dadata_party[0])
                self._merge_practice_context_into_description(payload, org, context)
                await self._core.import_organizer(payload)
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            await self._core.update_source(source_id, last_crawled_at=now)
            logger.info(
                "silverage_source_crawled",
                source_id=source_id,
                base_url=base_url[:60],
            )
        except Exception as exc:
            logger.warning(
                "silverage_crawl_source_failed",
                source_id=source_id,
                base_url=(base_url or "")[:60],
                error=str(exc),
            )

    async def _get_platform_organizer_id(self) -> Optional[str]:
        """Return organizer_id for Silver Age platform (Коалиция «Забота рядом»). Creates if missing."""
        if getattr(self, "_platform_organizer_id", None):
            return self._platform_organizer_id
        data = await self._core.lookup_organization(source_reference="silverage_platform")
        if data and data.get("organizer_id"):
            self._platform_organizer_id = data["organizer_id"]
            return self._platform_organizer_id
        payload = {
            "source_reference": "silverage_platform",
            "entity_type": "Organization",
            "title": "Коалиция «Забота рядом» / silveragemap.ru",
            "description": "Агрегатор практик и мероприятий для людей старшего возраста.",
            "ai_metadata": {
                "decision": "accepted",
                "ai_confidence_score": 0.95,
                "works_with_elderly": True,
                "ai_explanation": "Платформа-агрегатор для импорта мероприятий Silver Age.",
                "ai_source_trace": [
                    {"source_kind": "platform_silverage", "source_url": "https://silveragemap.ru/meropriyatiya/", "fields_extracted": ["events_list"]},
                ],
            },
            "classification": {
                "organization_type_codes": ["142"],
                "ownership_type_code": "162",
                "thematic_category_codes": [],
                "service_codes": [],
                "specialist_profile_codes": [],
            },
            "venues": [],
        }
        resp = await self._core.import_organizer(payload)
        self._platform_organizer_id = resp.get("organizer_id")
        return self._platform_organizer_id

    async def _process_event(
        self,
        event: SilverAgeEvent,
        dry_run: bool = False,
    ) -> EventResult:
        result = EventResult(
            title=event.title,
            date_text=event.date_text,
            location=event.location,
            page_url=event.page_url,
        )

        if dry_run:
            result.action = "dry_run"
            return result

        try:
            organizer_id = await self._get_platform_organizer_id()
            if not organizer_id:
                result.action = "error"
                result.error = "Platform organizer not available"
                return result

            raw = silverage_event_to_raw(event)
            desc_override = (event.description or "").strip()[:2000]
            if event.page_url:
                desc_override = f"{desc_override}\n\nСтраница мероприятия: {event.page_url}".strip()

            payload = run_event_ingestion_pipeline(
                raw,
                organizer_id,
                use_llm_classification=True,
                title_override=event.title,
                description_override=desc_override or None,
            )
            if payload is None:
                result.action = "rejected"
                return result
            await self._core.import_event(payload)
            result.action = "created"

        except Exception as e:
            result.action = "error"
            result.error = str(e)

        return result

    def _init_search_provider(self) -> Optional[object]:
        try:
            from search.provider import get_search_provider
            return get_search_provider()
        except Exception:
            return None

    async def _create_source_record(
        self,
        organizer_id: str,
        website_url: str,
        kind: str = "org_website",
    ) -> None:
        """Create a source record in Core API for the discovered website."""
        try:
            await self._core.create_source(
                organizer_id=organizer_id,
                base_url=website_url,
                kind=kind,
            )
            logger.info("Source record created", organizer_id=organizer_id, url=website_url)
        except Exception as exc:
            logger.warning("Failed to create source record", error=str(exc))

    async def _enrich_venues(self, payload: dict) -> Optional[list[dict]]:
        """Enrich venue addresses with Dadata geocoding."""
        venues = payload.get("venues", [])
        if not venues:
            return None

        enriched = []
        for v in venues:
            addr = v.get("address_raw", "")
            if not addr:
                continue
            geo = await self._dadata.geocode(addr)
            enriched.append({
                "address_raw": addr,
                "fias_id": geo.fias_id,
                "fias_level": geo.fias_level,
                "city_fias_id": geo.city_fias_id,
                "region_iso": geo.region_iso,
                "region_code": geo.region_code,
                "kladr_id": geo.kladr_id,
                "geo_lat": geo.geo_lat,
                "geo_lon": geo.geo_lon,
                "is_headquarters": v.get("is_headquarters", True),
            })

        return enriched if enriched else None

    async def _create_minimal_org(
        self,
        org: SilverAgeOrganization,
        inn: str = "",
        *,
        dadata_party: Optional[list] = None,
    ) -> dict:
        """Create minimal org; use precomputed Dadata party when provided (no extra API calls)."""
        practice_titles = ", ".join(f"«{p.title}»" for p in org.practices[:3])
        description = (
            f"{org.best_description[:500]} "
            f"Практики: {practice_titles}."
        )

        party_name = org.name
        address_raw = org.region
        venue: dict = {"address_raw": address_raw}
        contacts: dict = {"phones": [], "emails": []}
        use_party = dadata_party and len(dadata_party) > 0
        party_obj = dadata_party[0] if use_party else None

        if use_party and party_obj:
            party_name = getattr(party_obj, "name_short", None) or party_name
            address_raw = getattr(party_obj, "address", None) or address_raw
            try:
                geo = party_obj.to_geocoding_result()
                venue = {"address_raw": geo.address_raw, "address_comment": "адрес из реестра Dadata"}
                if geo.fias_id:
                    venue["fias_id"] = geo.fias_id
                if geo.fias_level:
                    venue["fias_level"] = geo.fias_level
                if geo.city_fias_id:
                    venue["city_fias_id"] = geo.city_fias_id
                if geo.region_iso:
                    venue["region_iso"] = geo.region_iso
                if geo.region_code:
                    venue["region_code"] = geo.region_code
                if geo.kladr_id:
                    venue["kladr_id"] = geo.kladr_id
                if geo.geo_lat is not None and geo.geo_lon is not None:
                    venue["geo_lat"] = geo.geo_lat
                    venue["geo_lon"] = geo.geo_lon
                venue["is_headquarters"] = True
            except Exception:
                venue = {"address_raw": address_raw}
            contacts["phones"] = list(getattr(party_obj, "phones", None) or [])
            contacts["emails"] = list(getattr(party_obj, "emails", None) or [])
        elif inn:
            party = await self._dadata.find_party_by_id(inn)
            if party.found:
                party_name = party.name_short or party_name
                address_raw = party.address or address_raw
                geo = party.to_geocoding_result()
                venue = {"address_raw": address_raw}
                if geo.fias_id:
                    venue.update({
                        "fias_id": geo.fias_id,
                        "fias_level": geo.fias_level,
                        "city_fias_id": geo.city_fias_id,
                        "region_iso": geo.region_iso,
                        "region_code": geo.region_code,
                        "kladr_id": geo.kladr_id,
                        "geo_lat": geo.geo_lat,
                        "geo_lon": geo.geo_lon,
                        "is_headquarters": True,
                    })
                contacts["phones"] = list(getattr(party, "phones", None) or [])
                contacts["emails"] = list(getattr(party, "emails", None) or [])

        payload = {
            "source_reference": org.source_reference,
            "entity_type": "Organization",
            "title": party_name,
            "description": description,
            "ai_metadata": {
                "decision": "needs_review",
                "ai_confidence_score": 0.60,
                "works_with_elderly": True,
                "ai_explanation": (
                    f"Организация из базы практик silveragemap.ru. "
                    f"Все практики на сайте посвящены работе с пожилыми людьми. "
                    f"Регион: {org.region}. Практик: {org.practice_count}."
                ),
                "ai_source_trace": [
                    {
                        "source_kind": "platform_silverage",
                        "source_url": org.practices[0].page_url if org.practices else "https://silveragemap.ru",
                        "fields_extracted": ["org_name", "org_description", "region", "practice_title"],
                    }
                ],
            },
            "classification": {
                "organization_type_codes": ["142"],
                "ownership_type_code": "162",
                "thematic_category_codes": [],
                "service_codes": [],
                "specialist_profile_codes": [],
            },
            "venues": [venue] if address_raw else [],
            "contacts": contacts,
        }

        if inn:
            payload["inn"] = inn
        if use_party and party_obj and getattr(party_obj, "ogrn", None):
            payload["ogrn"] = party_obj.ogrn

        if not venue.get("fias_id"):
            geo_venues = await self._enrich_venues(payload)
            if geo_venues:
                payload["venues"] = geo_venues

        return await self._core.import_organizer(payload)

    def _save_report(self, report: PipelineReport, path: str) -> None:
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Report saved", path=path)
