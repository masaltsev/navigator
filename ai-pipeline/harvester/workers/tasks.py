"""
Celery tasks for Harvester.

Tasks wrap the async pipeline (Crawl4AI + DeepSeek + Dadata + Core API)
and run it inside asyncio.run() within Celery worker processes.

Two main tasks:
  - crawl_and_enrich: process a single URL (full pipeline)
  - process_batch: fan-out a list of source records to individual tasks
"""

import asyncio
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
from celery import group

from workers.celery_app import app

from config.settings import get_settings

settings = get_settings()

_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))

from config.logging import configure_logging

configure_logging()

logger = structlog.get_logger(__name__)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


def _is_source_id_updatable(source_id: str) -> bool:
    return bool(source_id and source_id not in ("celery", "api") and _UUID_RE.match(source_id))


async def _maybe_update_source_after_crawl(
    core_client: Optional[object],
    source_id: str,
    last_status: str,
) -> None:
    if not core_client or not _is_source_id_updatable(source_id):
        return
    try:
        await core_client.update_source(
            source_id,
            last_status=last_status,
            last_crawled_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.warning("Failed to update source %s after crawl: %s", source_id[:12], e)


async def _run_pipeline(
    url: str,
    source_id: str = "celery",
    source_item_id: Optional[str] = None,
    existing_entity_id: Optional[str] = None,
    multi_page: bool = True,
    enrich_geo: bool = True,
    send_to_core: bool = True,
) -> dict:
    """
    Full async pipeline: crawl → classify → [Dadata] → [Core API].

    Designed to run inside asyncio.run() from a Celery task.
    """
    from core_client.api import NavigatorCoreClient
    from harvest.run_organization_harvest import run_organization_harvest

    core_client = None
    if send_to_core:
        core_client = NavigatorCoreClient(
            base_url=settings.core_api_url,
            api_token=settings.core_api_token,
        )

    t_start = time.time()
    out = await run_organization_harvest(
        url,
        source_id=source_id,
        source_item_id=source_item_id,
        existing_entity_id=existing_entity_id,
        multi_page=multi_page,
        enrich_geo=enrich_geo,
        additional_context="",
        source_kind="org_website",
        try_site_extractor=False,
        deepseek_client=None,
    )

    if not out["success"]:
        await _maybe_update_source_after_crawl(core_client, source_id, "error")
        return {
            "status": "error",
            "error": out.get("error", "unknown"),
            "url": url,
            **out.get("crawl_meta", {}),
        }

    result = out["result"]
    payload = out["payload"]
    crawl_meta = out["crawl_meta"]
    geo_results = out.get("geo_results")
    llm_metrics = out.get("llm_metrics", {})

    core_response = None
    if send_to_core and core_client:
        core_response = await core_client.import_organizer(payload)

    await _maybe_update_source_after_crawl(core_client, source_id, "success")

    t_end = time.time()
    venues_geocoded = sum(1 for g in (geo_results or []) if g.fias_id) if geo_results else 0

    return {
        "status": "success",
        "url": url,
        "title": result.title,
        "decision": result.ai_metadata.decision,
        "confidence": result.ai_metadata.ai_confidence_score,
        "works_with_elderly": result.ai_metadata.works_with_elderly,
        "venues_count": len(result.venues),
        "venues_geocoded": venues_geocoded,
        "core_response": core_response,
        "timing": {
            "total_s": round(t_end - t_start, 1),
        },
        "llm_metrics": llm_metrics,
        **crawl_meta,
    }


@app.task(
    bind=True,
    name="workers.tasks.crawl_and_enrich",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def crawl_and_enrich(
    self,
    url: str,
    source_id: str = "celery",
    source_item_id: Optional[str] = None,
    existing_entity_id: Optional[str] = None,
    multi_page: bool = True,
    enrich_geo: bool = True,
    send_to_core: bool = True,
) -> dict:
    """
    Celery task: full pipeline for a single URL.

    Wraps the async pipeline in asyncio.run(). Retries on transient errors.
    """
    logger.info("Processing URL: %s (source=%s, multi_page=%s)", url, source_id, multi_page)

    try:
        result = asyncio.run(
            _run_pipeline(
                url=url,
                source_id=source_id,
                source_item_id=source_item_id,
                existing_entity_id=existing_entity_id,
                multi_page=multi_page,
                enrich_geo=enrich_geo,
                send_to_core=send_to_core,
            )
        )
        logger.info(
            "Completed: %s — %s (confidence=%.2f, time=%.1fs)",
            url,
            result.get("decision", "?"),
            result.get("confidence", 0),
            result.get("timing", {}).get("total_s", 0),
        )
        return result

    except Exception as exc:
        logger.error("Task failed for %s: %s", url, exc)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        return {
            "status": "error",
            "error": str(exc),
            "url": url,
            "retries_exhausted": True,
        }


@app.task(
    bind=True,
    name="workers.tasks.harvest_events",
    max_retries=1,
    default_retry_delay=30,
    acks_late=True,
)
def harvest_events(
    self,
    url: str,
    source_id: str = "celery",
    max_event_pages: int = 3,
    max_events_per_page: int = 10,
    send_to_core: bool = True,
) -> dict:
    """
    Celery task: discover and classify events from an organization's website.

    Crawls /news, /afisha pages → splits into event candidates →
    classifies each via EventProcessor + DeepSeek.
    """
    logger.info("harvest_events_start", url=url, source_id=source_id)

    try:
        result = asyncio.run(
            _run_event_pipeline(
                url=url,
                source_id=source_id,
                max_event_pages=max_event_pages,
                max_events_per_page=max_events_per_page,
                send_to_core=send_to_core,
            )
        )
        logger.info(
            "harvest_events_complete",
            url=url,
            candidates=result.get("candidates_found", 0),
            classified=result.get("events_classified", 0),
        )
        return result

    except Exception as exc:
        logger.error("harvest_events_failed", url=url, error=str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        return {
            "status": "error",
            "error": str(exc),
            "url": url,
            "retries_exhausted": True,
        }


async def _run_event_pipeline(
    url: str,
    source_id: str = "celery",
    max_event_pages: int = 3,
    max_events_per_page: int = 10,
    send_to_core: bool = True,
) -> dict:
    """Async event harvesting pipeline via universal event ingestion."""
    from core_client.api import NavigatorCoreClient
    from event_ingestion import event_candidate_to_raw, run_event_ingestion_pipeline
    from processors.deepseek_client import DeepSeekClient
    from processors.event_processor import EventProcessor
    from strategies.event_discovery import EventDiscoverer

    discoverer = EventDiscoverer(
        max_event_pages=max_event_pages,
        max_events_per_page=max_events_per_page,
    )
    discovery = await discoverer.discover_events(url)

    if not discovery.candidates:
        return {
            "status": "no_events",
            "url": url,
            "event_pages_found": discovery.event_pages_found,
        }

    organizer_id = None
    core_client = None
    if send_to_core:
        core_client = NavigatorCoreClient(
            base_url=settings.core_api_url,
            api_token=settings.core_api_token,
        )
        source = await core_client.get_source(source_id)
        if source and source.get("organizer_id"):
            organizer_id = source["organizer_id"]
        if not organizer_id:
            send_to_core = False

    client = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model_name,
    )
    processor = EventProcessor(deepseek_client=client)

    events: list[dict] = []
    for candidate in discovery.candidates:
        try:
            raw = event_candidate_to_raw(candidate, source_id)
            payload = run_event_ingestion_pipeline(
                raw,
                organizer_id or "",
                event_processor=processor,
                use_llm_classification=True,
            )
            if not organizer_id:
                events.append({"payload": payload, "organizer_id_required": True})
                continue

            if send_to_core and core_client:
                core_response = await core_client.import_event(payload)
                payload["_core_response"] = core_response

            events.append(payload)
        except Exception as e:
            events.append({"error": str(e), "candidate_title": candidate.title})

    return {
        "status": "success",
        "url": url,
        "event_pages_found": discovery.event_pages_found,
        "candidates_found": len(discovery.candidates),
        "events_classified": len([e for e in events if "error" not in e]),
        "events": events,
        "llm_metrics": client.get_metrics(),
    }


@app.task(
    bind=True,
    name="workers.tasks.process_sonko_batch",
    max_retries=0,
    acks_late=True,
)
def process_sonko_batch(
    self,
    xlsx_path: str,
    limit: int | None = None,
    dry_run: bool = False,
    include_broader_okved: bool = False,
) -> dict:
    """
    Celery task: run the SONKO registry pipeline.

    Parses the XLSX, filters by OKVED + name keywords,
    deduplicates by INN, then processes each through
    match_or_create -> website discovery -> harvest.
    """
    logger.info("sonko_batch_start", xlsx=xlsx_path, limit=limit, dry_run=dry_run)

    try:
        from aggregators.sonko.sonko_pipeline import SONKOPipeline

        pipeline = SONKOPipeline()
        report = asyncio.run(
            pipeline.run(
                xlsx_path=xlsx_path,
                limit=limit,
                dry_run=dry_run,
                include_broader_okved=include_broader_okved,
            )
        )

        return {
            "status": "success",
            "filter_stats": {
                "total_entries": report.filter_stats.total_entries,
                "combined_unique": report.filter_stats.combined_unique,
            },
            "summary": {
                "total": len(report.results),
                "matched": report.matched,
                "created": report.created,
                "errors": report.errors,
            },
        }

    except Exception as exc:
        logger.error("sonko_batch_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}


@app.task(
    bind=True,
    name="workers.tasks.process_fpg_batch",
    max_retries=0,
    acks_late=True,
)
def process_fpg_batch(
    self,
    xlsx_path: str,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Celery task: run the FPG aggregator pipeline.

    Parses the XLSX, filters for elderly-relevant projects,
    deduplicates by org, then processes each through
    match_or_create -> website discovery -> harvest.
    """
    logger.info("fpg_batch_start", xlsx=xlsx_path, limit=limit, dry_run=dry_run)

    try:
        from aggregators.fpg.fpg_pipeline import FPGPipeline

        pipeline = FPGPipeline()
        report = asyncio.run(
            pipeline.run(
                xlsx_path=xlsx_path,
                limit=limit,
                dry_run=dry_run,
            )
        )

        return {
            "status": "success",
            "filter_stats": {
                "total_input": report.filter_stats.total_input,
                "after_elderly": report.filter_stats.after_elderly,
                "unique_orgs": report.filter_stats.unique_organizations,
            },
            "summary": {
                "total": len(report.results),
                "matched": report.matched,
                "created": report.created,
                "errors": report.errors,
            },
        }

    except Exception as exc:
        logger.error("fpg_batch_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}


@app.task(
    bind=True,
    name="workers.tasks.process_silverage_batch",
    max_retries=0,
    acks_late=True,
)
def process_silverage_batch(
    self,
    max_pages: int | None = None,
    max_practices: int | None = None,
    limit_orgs: int | None = None,
    dry_run: bool = False,
    scrape_events: bool = True,
    cache_dir: str | None = None,
) -> dict:
    """
    Celery task: run the Silver Age (silveragemap.ru) scraper pipeline.

    Scrapes practices + events, extracts organizations,
    discovers websites, runs harvest or creates minimal records.
    """
    logger.info(
        "silverage_batch_start",
        max_pages=max_pages,
        limit_orgs=limit_orgs,
        dry_run=dry_run,
    )

    try:
        from aggregators.silverage.silverage_pipeline import SilverAgePipeline

        pipeline = SilverAgePipeline(cache_dir=cache_dir)
        report = asyncio.run(
            pipeline.run(
                max_pages=max_pages,
                max_practices=max_practices,
                limit_orgs=limit_orgs,
                dry_run=dry_run,
                scrape_events=scrape_events,
            )
        )

        return {
            "status": "success",
            "summary": {
                "total_practices": report.total_practices,
                "unique_organizations": report.unique_organizations,
                "total_events": report.total_events,
                "orgs_created": report.orgs_created,
                "orgs_matched": report.orgs_matched,
                "orgs_errors": report.orgs_errors,
            },
        }

    except Exception as exc:
        logger.error("silverage_batch_failed", error=str(exc))
        return {"status": "error", "error": str(exc)}


@app.task(
    name="workers.tasks.process_batch",
    acks_late=True,
)
def process_batch(
    sources: list[dict],
    multi_page: bool = True,
    enrich_geo: bool = True,
    send_to_core: bool = True,
) -> dict:
    """
    Fan-out: dispatch crawl_and_enrich for each source in the list.

    Each source dict should have:
        - url (str, required)
        - source_id (str, optional)
        - source_item_id (str, optional)
        - existing_entity_id (str, optional)

    Returns a group result summary.
    """
    if not sources:
        return {"status": "empty", "message": "No sources to process"}

    from enrichment.url_validator import filter_valid_urls

    valid_sources, invalid_sources = filter_valid_urls(sources)
    if invalid_sources:
        logger.warning(
            "harvest_invalid_urls_filtered",
            count=len(invalid_sources),
            urls=[s.get("url", "?") for s in invalid_sources],
        )

    tasks = []
    for src in valid_sources:
        url = src.get("url")
        if not url:
            continue
        tasks.append(
            crawl_and_enrich.s(
                url=url,
                source_id=src.get("source_id", "batch"),
                source_item_id=src.get("source_item_id"),
                existing_entity_id=src.get("existing_entity_id"),
                multi_page=multi_page,
                enrich_geo=enrich_geo,
                send_to_core=send_to_core,
            )
        )

    if not tasks:
        return {"status": "empty", "message": "No valid URLs in batch"}

    job = group(tasks)
    result = job.apply_async()

    logger.info(
        "harvest_batch_dispatched",
        tasks_count=len(tasks),
        group_id=str(result.id),
    )

    return {
        "status": "dispatched",
        "group_id": result.id,
        "tasks_count": len(tasks),
        "urls": [src["url"] for src in sources if src.get("url")],
    }
