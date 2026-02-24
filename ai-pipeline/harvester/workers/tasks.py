"""
Celery tasks for Harvester.

Tasks wrap the async pipeline (Crawl4AI + DeepSeek + Dadata + Core API)
and run it inside asyncio.run() within Celery worker processes.

Two main tasks:
  - crawl_and_enrich: process a single URL (full pipeline)
  - process_batch: fan-out a list of source records to individual tasks
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from celery import group
from celery.utils.log import get_task_logger

from workers.celery_app import app

_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))

logger = get_task_logger(__name__)


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
    from enrichment.dadata_client import DadataClient
    from processors.deepseek_client import DeepSeekClient
    from processors.organization_processor import OrganizationProcessor, to_core_import_payload
    from prompts.schemas import EntityType, HarvestInput
    from strategies.multi_page import MultiPageCrawler

    t_start = time.time()

    if multi_page:
        crawler = MultiPageCrawler(max_subpages=5)
        multi_result = await crawler.crawl_organization(url)
        if not multi_result.success:
            return {
                "status": "error",
                "error": "crawl_failed",
                "url": url,
                "pages_attempted": multi_result.total_pages_attempted,
            }
        markdown = multi_result.merged_markdown
        crawl_meta = {
            "pages_attempted": multi_result.total_pages_attempted,
            "pages_success": multi_result.total_pages_success,
        }
    else:
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        browser_config = BrowserConfig(
            headless=True, enable_stealth=True,
            user_agent=os.getenv("CRAWL4AI_USER_AGENT", ""),
        )
        run_config = CrawlerRunConfig(
            word_count_threshold=0, page_timeout=30000,
            wait_until="domcontentloaded", delay_before_return_html=2.0,
            magic=True, simulate_user=True, cache_mode=CacheMode.BYPASS,
        )
        async with AsyncWebCrawler(config=browser_config) as c:
            res = await c.arun(url=url, config=run_config)
        if not res.success:
            return {"status": "error", "error": "crawl_failed", "url": url}
        markdown = res.markdown or res.fit_markdown or ""
        crawl_meta = {"pages_attempted": 1, "pages_success": 1}

    if not markdown.strip():
        return {"status": "error", "error": "empty_markdown", "url": url}

    t_crawl = time.time()

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    client = DeepSeekClient(api_key=api_key)
    processor = OrganizationProcessor(deepseek_client=client)

    harvest_input = HarvestInput(
        source_id=source_id,
        source_item_id=source_item_id or url,
        entity_type=EntityType.ORGANIZATION,
        raw_text=markdown[:30000],
        source_url=url,
        source_kind="org_website",
        existing_entity_id=existing_entity_id,
    )

    result = processor.process(harvest_input)
    t_classify = time.time()

    geo_results = None
    if enrich_geo:
        dadata_key = os.getenv("DADATA_API_KEY", "")
        dadata_secret = os.getenv("DADATA_SECRET_KEY", "")
        use_clean = os.getenv("DADATA_USE_CLEAN", "false").lower() in ("true", "1")
        dadata = DadataClient(api_key=dadata_key, secret_key=dadata_secret, use_clean=use_clean)
        if dadata.enabled and result.venues:
            addresses = [v.address_raw for v in result.venues]
            geo_results = await dadata.geocode_batch(addresses)

    payload = to_core_import_payload(result, geo_results=geo_results)
    t_enrich = time.time()

    core_response = None
    if send_to_core:
        core_url = os.getenv("CORE_API_URL", "")
        core_token = os.getenv("CORE_API_TOKEN", "")
        core_client = NavigatorCoreClient(base_url=core_url, api_token=core_token)
        core_response = await core_client.import_organizer(payload)

    t_end = time.time()

    metrics = client.get_metrics()

    return {
        "status": "success",
        "url": url,
        "title": result.title,
        "decision": result.ai_metadata.decision,
        "confidence": result.ai_metadata.ai_confidence_score,
        "works_with_elderly": result.ai_metadata.works_with_elderly,
        "venues_count": len(result.venues),
        "venues_geocoded": sum(1 for g in (geo_results or []) if g.fias_id),
        "core_response": core_response,
        "timing": {
            "crawl_s": round(t_crawl - t_start, 1),
            "classify_s": round(t_classify - t_crawl, 1),
            "enrich_s": round(t_enrich - t_classify, 1),
            "core_s": round(t_end - t_enrich, 1),
            "total_s": round(t_end - t_start, 1),
        },
        "llm_metrics": metrics,
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

    tasks = []
    for src in sources:
        url = src.get("url")
        if not url:
            logger.warning("Skipping source without URL: %s", src)
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
        "Batch dispatched: %d tasks (group_id=%s)",
        len(tasks), result.id,
    )

    return {
        "status": "dispatched",
        "group_id": result.id,
        "tasks_count": len(tasks),
        "urls": [src["url"] for src in sources if src.get("url")],
    }
