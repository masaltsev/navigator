"""End-to-end SONKO registry pipeline.

Flow:
  1. Parse XLSX -> list[SONKOEntry]
  2. Filter: OKVED ∪ name keywords -> dedup by INN
  3. For each unique SONKOOrganization:
     a. Lookup in Core by INN (existing org?)
     b. If exists: log match, skip
     c. If new:
        - Dadata findPartyById(INN) for official address
        - Web search for org website (reuse source_discoverer)
        - If website found: full harvest pipeline
        - If not: create minimal org from SONKO + Dadata data
  4. Report summary

Structurally similar to the FPG pipeline, but simpler: no project-level
data to classify -- we import organizations directly from registry.
"""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from aggregators.sonko.models import SONKOOrganization
from aggregators.sonko.org_filter import FilterStats, run_filter_pipeline
from aggregators.sonko.xlsx_parser import parse_xlsx
from config.settings import get_settings
from core_client.api import NavigatorCoreClient
from enrichment.dadata_client import DadataClient

logger = structlog.get_logger(__name__)
settings = get_settings()


@dataclass
class OrgProcessingResult:
    inn: str
    name: str
    okved: str
    address: str
    action: str = ""
    core_organizer_id: Optional[str] = None
    discovered_website: Optional[str] = None
    harvest_decision: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "inn": self.inn,
            "name": self.name,
            "okved": self.okved,
            "address": self.address[:80] if self.address else "",
            "action": self.action,
            "core_organizer_id": self.core_organizer_id,
            "discovered_website": self.discovered_website,
            "harvest_decision": self.harvest_decision,
            "error": self.error,
        }


@dataclass
class PipelineReport:
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
            "=== SONKO Pipeline Report ===",
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
                "total_entries": self.filter_stats.total_entries,
                "unique_inns_total": self.filter_stats.unique_inns_total,
                "after_okved": self.filter_stats.after_okved,
                "after_name_kw": self.filter_stats.after_name_kw,
                "combined_unique": self.filter_stats.combined_unique,
            },
            "results": [r.to_dict() for r in self.results],
            "summary": {
                "total": len(self.results),
                "matched": self.matched,
                "created": self.created,
                "errors": self.errors,
            },
        }


class SONKOPipeline:
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
        include_broader_okved: bool = False,
        output_path: Optional[str] = None,
    ) -> PipelineReport:
        report = PipelineReport()

        logger.info("SONKO pipeline starting", xlsx=xlsx_path, limit=limit, dry_run=dry_run)

        entries = parse_xlsx(xlsx_path)
        organizations, stats = run_filter_pipeline(
            entries, include_broader_okved=include_broader_okved
        )
        report.filter_stats = stats

        logger.info(
            "SONKO filter complete",
            orgs=len(organizations),
        )

        if limit:
            organizations = organizations[:limit]

        for i, org in enumerate(organizations):
            logger.info(
                "Processing SONKO org",
                progress=f"{i+1}/{len(organizations)}",
                inn=org.inn,
                name=org.full_name[:60],
                okved=org.okved,
            )

            result = await self._process_organization(org, dry_run=dry_run)
            report.results.append(result)

            if i < len(organizations) - 1 and self._delay > 0:
                await asyncio.sleep(self._delay)

        logger.info("SONKO pipeline complete\n" + report.summary())

        if output_path:
            self._save_report(report, output_path)

        return report

    async def analyze_only(
        self,
        xlsx_path: str,
        include_broader_okved: bool = False,
    ) -> FilterStats:
        entries = parse_xlsx(xlsx_path)
        _, stats = run_filter_pipeline(
            entries, include_broader_okved=include_broader_okved
        )
        return stats

    @staticmethod
    def _build_sonko_context(org: SONKOOrganization) -> str:
        """Build additional context from SONKO registry for LLM input."""
        parts = [
            f"[Контекст из реестра СО НКО Минэкономразвития]",
            f"Организация: {org.full_name}",
        ]
        if org.short_name:
            parts.append(f"Сокращённое название: {org.short_name}")

        parts.append(f"ИНН: {org.inn}, ОГРН: {org.ogrn}")
        parts.append(f"Адрес: {org.address}")
        parts.append(f"ОКВЭД: {org.okved}")

        if org.legal_form:
            parts.append(f"ОПФ: {org.legal_form}")

        if org.all_statuses:
            parts.append(f"Статусы СОНКО: {', '.join(sorted(org.all_statuses))}")
        if org.all_criteria:
            parts.append(f"Критерии включения: {', '.join(sorted(org.all_criteria))}")

        parts.append(
            "\nОрганизация отфильтрована по ОКВЭД/ключевым словам, "
            "указывающим на работу с людьми старшего возраста."
        )
        return "\n".join(parts)

    async def _process_organization(
        self,
        org: SONKOOrganization,
        dry_run: bool = False,
    ) -> OrgProcessingResult:
        result = OrgProcessingResult(
            inn=org.inn,
            name=org.full_name,
            okved=org.okved,
            address=org.address,
        )

        try:
            existing = await self._core.lookup_organization(
                inn=org.inn,
                source_reference=org.source_reference,
            )

            context = self._build_sonko_context(org)

            if existing:
                result.action = "matched"
                result.core_organizer_id = existing.get("organizer_id")
                await self._update_matched_org(existing, org, context)
                logger.info("SONKO org matched existing", inn=org.inn)
                return result

            if dry_run:
                result.action = "dry_run"
                return result

            pipeline = self._get_enrichment_pipeline()
            if pipeline:
                city = org.region_from_address
                enrichment = await pipeline.enrich_missing_source(
                    org_title=org.short_name or org.full_name,
                    city=city,
                    inn=org.inn,
                    source_id=org.source_reference,
                    additional_context=context,
                    source_kind="registry_sonko",
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
            logger.error("Error processing SONKO org", inn=org.inn, error=str(e))

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
        org: SONKOOrganization,
        context: str,
    ) -> None:
        """Update an existing matched org with SONKO registry context."""
        organizer_id = existing.get("organizer_id")
        if not organizer_id:
            return

        statuses_str = ", ".join(org.all_statuses) if org.all_statuses else "СОНКО"
        payload = {
            "source_reference": org.source_reference,
            "entity_type": "Organization",
            "title": existing.get("title", org.full_name),
            "inn": org.inn,
            "ogrn": org.ogrn,
            "description": (
                f"{existing.get('description', '')}\n\n"
                f"Дополнительно из реестра СО НКО: статус {statuses_str}, "
                f"ОКВЭД {org.okved}."
            ).strip(),
            "ai_metadata": {
                "decision": existing.get("ai_metadata", {}).get("decision", "needs_review"),
                "ai_confidence_score": existing.get("ai_metadata", {}).get("ai_confidence_score", 0.6),
                "works_with_elderly": True,
                "ai_source_trace": existing.get("ai_metadata", {}).get("ai_source_trace", []) + [
                    {
                        "source_kind": "registry_sonko",
                        "source_url": "https://data.economy.gov.ru/analytics/sonko",
                        "fields_extracted": ["inn", "ogrn", "okved", "sonko_status"],
                    }
                ],
            },
        }

        try:
            await self._core.import_organizer(payload)
            logger.info("Matched org updated with SONKO context", organizer_id=organizer_id)
        except Exception as exc:
            logger.warning("Failed to update matched org", error=str(exc))

    async def _create_minimal_org(self, org: SONKOOrganization) -> dict:
        statuses_str = ", ".join(org.all_statuses) if org.all_statuses else "СОНКО"
        criteria_str = ", ".join(org.all_criteria) if org.all_criteria else ""

        description_parts = [
            f"Организация из реестра СО НКО Минэкономразвития.",
            f"ОКВЭД: {org.okved}.",
            f"Статус: {statuses_str}.",
        ]
        if criteria_str:
            description_parts.append(f"Критерий: {criteria_str}.")

        party = await self._dadata.find_party_by_id(org.inn)
        address_raw = party.address if party.address else org.address
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
            "title": party.name_short or org.full_name,
            "description": " ".join(description_parts),
            "inn": org.inn,
            "ogrn": org.ogrn,
            "ai_metadata": {
                "decision": "needs_review",
                "ai_confidence_score": 0.45,
                "works_with_elderly": True,
                "ai_explanation": (
                    f"Организация из реестра СО НКО. "
                    f"ОКВЭД {org.okved} относится к социальному обслуживанию. "
                    f"Сайт организации не найден — требуется ручная проверка."
                ),
                "ai_source_trace": [
                    {
                        "source_kind": "registry_sonko",
                        "source_url": "https://data.economy.gov.ru/analytics/sonko",
                        "fields_extracted": ["inn", "ogrn", "full_name", "address", "okved", "sonko_status"],
                    }
                ],
            },
            "classification": {
                "organization_type_codes": self._infer_org_type(org),
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

    def _infer_org_type(self, org: SONKOOrganization) -> list[str]:
        """Infer Navigator organization type codes from OKVED."""
        prefix = org.okved_prefix
        codes = ["142"]  # НКО by default
        if prefix == "87":
            codes.append("141")  # Стационарное учреждение
        if prefix == "88" and org.is_social_service_provider:
            codes.append("143")  # Поставщик социальных услуг
        return codes


    async def _enrich_venues(self, payload: dict) -> Optional[list[dict]]:
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
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Report saved", path=path)
