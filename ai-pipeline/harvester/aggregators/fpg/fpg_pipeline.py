"""End-to-end FPG aggregator pipeline.

Flow:
  1. Parse XLSX -> list[FPGProject]
  2. Filter: direction -> status -> elderly keywords -> dedup by org
  3. For each unique FPGOrganization:
     a. Lookup in Core by INN (existing org?)
     b. If exists: log match, optionally update ai_source_trace
     c. If new:
        - Dadata findPartyById(INN) for official address
        - Web search for org website (reuse source_discoverer)
        - If website found: full harvest pipeline (crawl + classify)
        - If not: create minimal org record from FPG + Dadata data
  4. Report summary

Reuses existing Harvester infrastructure:
  - search/source_discoverer.py for website discovery
  - search/duckduckgo_provider.py or yandex as search backend
  - enrichment/dadata_client.py for geocoding + party lookup
  - processors/organization_processor.py for LLM classification
  - core_client/api.py for Core API calls
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from aggregators.fpg.models import FPGOrganization, FPGProject
from aggregators.fpg.project_filter import FilterStats, run_filter_pipeline
from aggregators.fpg.xlsx_parser import parse_xlsx
from config.settings import get_settings
from core_client.api import NavigatorCoreClient
from enrichment.dadata_client import DadataClient

logger = structlog.get_logger(__name__)
settings = get_settings()


@dataclass
class OrgProcessingResult:
    """Result of processing one FPG organization."""

    inn: str
    name: str
    region: str
    project_count: int
    has_winner: bool

    action: str = ""  # "matched", "created", "created_minimal", "skipped", "error"
    core_organizer_id: Optional[str] = None
    discovered_website: Optional[str] = None
    harvest_decision: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "inn": self.inn,
            "name": self.name,
            "region": self.region,
            "project_count": self.project_count,
            "has_winner": self.has_winner,
            "action": self.action,
            "core_organizer_id": self.core_organizer_id,
            "discovered_website": self.discovered_website,
            "harvest_decision": self.harvest_decision,
            "error": self.error,
        }


@dataclass
class PipelineReport:
    """Full report from an FPG pipeline run."""

    filter_stats: FilterStats = field(default_factory=FilterStats)
    results: list[OrgProcessingResult] = field(default_factory=list)

    @property
    def matched(self) -> int:
        return sum(1 for r in self.results if r.action == "matched")

    @property
    def created(self) -> int:
        return sum(1 for r in self.results if r.action in ("created", "created_minimal"))

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.action == "error")

    def summary(self) -> str:
        lines = [
            "=== FPG Pipeline Report ===",
            self.filter_stats.summary(),
            "",
            f"Processed organizations:  {len(self.results)}",
            f"  Matched existing:       {self.matched}",
            f"  Created new:            {self.created}",
            f"  Errors:                 {self.errors}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "filter_stats": {
                "total_input": self.filter_stats.total_input,
                "after_direction": self.filter_stats.after_direction,
                "after_status": self.filter_stats.after_status,
                "after_elderly": self.filter_stats.after_elderly,
                "unique_organizations": self.filter_stats.unique_organizations,
            },
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "total": len(self.results),
                "matched": self.matched,
                "created": self.created,
                "errors": self.errors,
            },
        }


class FPGPipeline:
    """End-to-end FPG aggregator pipeline."""

    def __init__(
        self,
        core_client: Optional[NavigatorCoreClient] = None,
        dadata_client: Optional[DadataClient] = None,
        search_provider: Optional[object] = None,
        delay_between_orgs: float = 1.0,
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
        self._delay = delay_between_orgs

    async def run(
        self,
        xlsx_path: str,
        limit: Optional[int] = None,
        dry_run: bool = False,
        directions: Optional[set[str]] = None,
        output_path: Optional[str] = None,
    ) -> PipelineReport:
        """Run the full FPG pipeline.

        Args:
            xlsx_path: Path to the FPG open data XLSX file.
            limit: Max organizations to process (after filtering).
            dry_run: If True, don't send to Core API.
            directions: Override default relevant directions.
            output_path: Write results JSON to this path.
        """
        report = PipelineReport()

        logger.info("FPG pipeline starting", xlsx=xlsx_path, limit=limit, dry_run=dry_run)

        projects = parse_xlsx(xlsx_path)
        organizations, stats = run_filter_pipeline(projects, directions)
        report.filter_stats = stats

        logger.info(
            "FPG filter complete",
            orgs=len(organizations),
            projects=stats.after_elderly,
        )

        if limit:
            organizations = organizations[:limit]

        for i, org in enumerate(organizations):
            logger.info(
                "Processing FPG org",
                progress=f"{i+1}/{len(organizations)}",
                inn=org.inn,
                name=org.name[:60],
                projects=org.project_count,
            )

            result = await self._process_organization(org, dry_run=dry_run)
            report.results.append(result)

            if i < len(organizations) - 1 and self._delay > 0:
                await asyncio.sleep(self._delay)

        logger.info("FPG pipeline complete\n" + report.summary())

        if output_path:
            self._save_report(report, output_path)

        return report

    async def analyze_only(self, xlsx_path: str) -> FilterStats:
        """Parse and filter without processing -- just return statistics."""
        projects = parse_xlsx(xlsx_path)
        _, stats = run_filter_pipeline(projects)
        return stats

    @staticmethod
    def _build_project_context(org: FPGOrganization) -> str:
        """Build additional context from FPG projects for LLM input."""
        parts = [
            f"[Контекст из каталога Фонда президентских грантов]",
            f"Организация: {org.name}",
            f"ИНН: {org.inn}, ОГРН: {org.ogrn}",
            f"Регион: {org.region}",
            f"Грантовые направления: {', '.join(sorted(org.all_directions))}",
            f"Всего проектов: {org.project_count}",
        ]

        for i, p in enumerate(org.projects[:5], 1):
            status = "✓ победитель" if p.is_winner else p.status
            parts.append(f"\nПроект {i}: «{p.project_title}»")
            parts.append(f"Направление: {p.grant_direction}")
            parts.append(f"Статус: {status}")
            if p.grant_amount:
                parts.append(f"Грант: {p.grant_amount:,.0f} руб.")

        parts.append(
            "\nПроекты содержат ключевые слова, указывающие на работу "
            "с людьми старшего возраста."
        )
        return "\n".join(parts)

    async def _process_organization(
        self,
        org: FPGOrganization,
        dry_run: bool = False,
    ) -> OrgProcessingResult:
        """Process a single FPG organization through the pipeline."""
        result = OrgProcessingResult(
            inn=org.inn,
            name=org.name,
            region=org.region,
            project_count=org.project_count,
            has_winner=org.has_winning_project,
        )

        try:
            existing = await self._core.lookup_organization(
                inn=org.inn,
                source_reference=org.source_reference,
            )

            context = self._build_project_context(org)

            if existing:
                result.action = "matched"
                result.core_organizer_id = existing.get("organizer_id")
                await self._update_matched_org(existing, org, context)
                logger.info(
                    "FPG org matched existing",
                    inn=org.inn,
                    organizer_id=result.core_organizer_id,
                )
                return result

            if dry_run:
                result.action = "dry_run"
                return result

            pipeline = self._get_enrichment_pipeline()
            if pipeline:
                enrichment = await pipeline.enrich_missing_source(
                    org_title=org.name,
                    city=org.region,
                    inn=org.inn,
                    source_id=org.source_reference,
                    additional_context=context,
                    source_kind="registry_fpg",
                )

                if enrichment.success and enrichment.harvest_output:
                    payload = enrichment.harvest_output
                    payload["source_reference"] = org.source_reference
                    if org.inn:
                        payload["inn"] = org.inn
                    if org.ogrn:
                        payload["ogrn"] = org.ogrn
                    import_result = await self._core.import_organizer(payload)
                    result.action = "created"
                    result.discovered_website = enrichment.verified_url
                    result.harvest_decision = import_result.get("assigned_status")
                    result.core_organizer_id = import_result.get("organizer_id")
                    if result.core_organizer_id and enrichment.verified_url:
                        await self._create_source_record(
                            result.core_organizer_id, enrichment.verified_url,
                        )
                    return result

            minimal_result = await self._create_minimal_org(org)
            result.action = "created_minimal"
            result.core_organizer_id = minimal_result.get("organizer_id")
            result.harvest_decision = minimal_result.get("assigned_status")

        except Exception as e:
            result.action = "error"
            result.error = str(e)
            logger.error("Error processing FPG org", inn=org.inn, error=str(e))

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

    def _init_search_provider(self) -> Optional[object]:
        try:
            from search.provider import get_search_provider
            return get_search_provider()
        except Exception:
            logger.warning("No search provider available")
            return None

    async def _update_matched_org(
        self,
        existing: dict,
        org: FPGOrganization,
        context: str,
    ) -> None:
        """Update an existing matched org with FPG project context."""
        organizer_id = existing.get("organizer_id")
        if not organizer_id:
            return

        best = org.best_project
        project_titles = ", ".join(f"«{t}»" for t in org.all_project_titles[:3])
        payload = {
            "source_reference": org.source_reference,
            "entity_type": "Organization",
            "title": existing.get("title", org.name),
            "inn": org.inn,
            "ogrn": org.ogrn,
            "description": (
                f"{existing.get('description', '')}\n\n"
                f"Дополнительно из каталога ФПГ: проекты {project_titles}. "
                f"Направление: {best.grant_direction}."
            ).strip(),
            "ai_metadata": {
                "decision": existing.get("ai_metadata", {}).get("decision", "needs_review"),
                "ai_confidence_score": existing.get("ai_metadata", {}).get("ai_confidence_score", 0.6),
                "works_with_elderly": True,
                "ai_source_trace": existing.get("ai_metadata", {}).get("ai_source_trace", []) + [
                    {
                        "source_kind": "registry_fpg",
                        "source_url": "https://президентскиегранты.рф/public/application/cards",
                        "fields_extracted": ["project_titles", "grant_direction", "inn", "ogrn"],
                    }
                ],
            },
        }

        try:
            await self._core.import_organizer(payload)
            logger.info(
                "Matched org updated with FPG context",
                organizer_id=organizer_id,
                projects=org.project_count,
            )
        except Exception as exc:
            logger.warning("Failed to update matched org", error=str(exc))

    async def _create_minimal_org(self, org: FPGOrganization) -> dict:
        """Create organization from FPG + Dadata data without website harvest."""
        best = org.best_project

        description_parts = [
            f"Организация-заявитель Фонда президентских грантов.",
            f"Регион: {org.region}.",
        ]
        if org.has_winning_project:
            description_parts.append(
                f"Победитель конкурса с проектом: «{best.project_title}»."
            )
        else:
            description_parts.append(f"Проект: «{best.project_title}».")

        party = await self._dadata.find_party_by_id(org.inn)
        address_raw = party.address if party.address else org.region
        geo = party.to_geocoding_result() if party.found else None

        venue = {"address_raw": address_raw}
        if geo and geo.fias_id:
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

        payload = {
            "source_reference": org.source_reference,
            "entity_type": "Organization",
            "title": party.name_short or org.name,
            "description": " ".join(description_parts),
            "inn": org.inn,
            "ogrn": org.ogrn,
            "ai_metadata": {
                "decision": "needs_review",
                "ai_confidence_score": 0.50,
                "works_with_elderly": True,
                "ai_explanation": (
                    f"Организация найдена в каталоге ФПГ. "
                    f"Проект '{best.project_title[:80]}' по направлению "
                    f"'{best.grant_direction}' содержит ключевые слова, "
                    f"указывающие на работу с пожилыми людьми. "
                    f"Сайт организации не найден — требуется ручная проверка."
                ),
                "ai_source_trace": [
                    {
                        "source_kind": "registry_fpg",
                        "source_url": "https://президентскиегранты.рф/public/application/cards",
                        "collected_at": best.start_date.isoformat() if best.start_date else None,
                        "fields_extracted": ["title", "inn", "ogrn", "region", "grant_direction"],
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
        }

        return await self._core.import_organizer(payload)


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

    def _save_report(self, report: PipelineReport, path: str) -> None:
        """Save pipeline report to JSON file."""
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Report saved", path=path)
