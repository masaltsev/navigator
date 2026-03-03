#!/usr/bin/env python3
"""
CLI: crawl one URL with Crawl4AI, classify via OrganizationProcessor + DeepSeek,
optionally enrich with Dadata and send to Navigator Core API.

Usage:
  cd ai-pipeline/harvester

  # Basic: crawl + classify
  python -m scripts.run_single_url https://example.com --pretty

  # Multi-page: crawl main + subpages (/kontakty, /o-nas, /uslugi)
  python -m scripts.run_single_url https://example.com --multi-page --pretty

  # Full E2E: multi-page crawl → classify → Dadata → Core API
  python -m scripts.run_single_url https://example.com --to-core --multi-page --pretty

  # Crawl + classify + Dadata enrichment (no Core send)
  python -m scripts.run_single_url https://example.com --enrich-geo --pretty

  # Crawl only (no LLM)
  python -m scripts.run_single_url https://example.com --crawl-only

  # Check env vars
  python -m scripts.run_single_url --check-env
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))

_env_file = _harvester_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

import structlog

from config.logging import configure_logging
from config.settings import get_settings
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

configure_logging()
settings = get_settings()
logger = structlog.get_logger("run_single_url")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)


async def crawl(url: str, save_raw_path: str | None = None) -> str:
    """Crawl URL, return markdown text (no LLM)."""
    browser_config = BrowserConfig(
        headless=settings.crawl4ai_headless,
        enable_stealth=True,
        user_agent=settings.crawl4ai_user_agent or _USER_AGENT,
        user_data_dir=settings.get_crawl4ai_browser_data_dir(),
    )
    run_config = CrawlerRunConfig(
        word_count_threshold=0,
        page_timeout=30000,
        wait_until="domcontentloaded",
        delay_before_return_html=2.0,
        magic=True,
        simulate_user=True,
        cache_mode=CacheMode.BYPASS,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=run_config)

    if save_raw_path:
        raw_dir = Path(save_raw_path)
        raw_dir.mkdir(parents=True, exist_ok=True)
        safe = url.replace("https://", "").replace("http://", "").rstrip("/").replace("/", "_")[:80]
        md = result.markdown or result.fit_markdown or ""
        html = getattr(result, "cleaned_html", "") or getattr(result, "raw_html", "") or ""
        if md:
            (raw_dir / f"{safe}_markdown.txt").write_text(md[:100000], encoding="utf-8")
        if html:
            (raw_dir / f"{safe}_cleaned_html.html").write_text(html[:200000], encoding="utf-8")
        logger.info("Raw content saved to %s", raw_dir)

    if not result.success:
        raise RuntimeError(result.error_message or "Crawl failed")

    return result.markdown or result.fit_markdown or ""


def classify(url: str, markdown: str) -> tuple:
    """Classify markdown via OrganizationProcessor → DeepSeek. Returns (result, payload, client)."""
    from processors.deepseek_client import DeepSeekClient
    from processors.organization_processor import OrganizationProcessor, to_core_import_payload
    from prompts.schemas import EntityType, HarvestInput

    client = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model_name,
    )
    processor = OrganizationProcessor(deepseek_client=client)

    harvest_input = HarvestInput(
        source_id="cli-single-url",
        source_item_id=url,
        entity_type=EntityType.ORGANIZATION,
        raw_text=markdown[:30000],
        source_url=url,
        source_kind="org_website",
    )

    t0 = time.time()
    result = processor.process(harvest_input)
    elapsed = time.time() - t0

    return result, elapsed, client


async def enrich_venues(result) -> list:
    """Geocode venues via Dadata. Returns list of GeocodingResult."""
    from enrichment.dadata_client import DadataClient

    dadata = DadataClient(
        api_key=settings.dadata_api_key,
        secret_key=settings.dadata_secret_key,
        use_clean=settings.dadata_use_clean,
    )

    if not dadata.enabled:
        logger.warning("Dadata keys not set — skipping geocoding")
        return []

    addresses = [v.address_raw for v in result.venues]
    if not addresses:
        return []

    geo_results = await dadata.geocode_batch(addresses)
    enriched = sum(1 for g in geo_results if g.fias_id)
    logger.info(
        "Dadata enrichment: %d/%d venues geocoded. Metrics: %s",
        enriched, len(addresses), dadata.get_metrics(),
    )
    return geo_results


async def send_to_core(payload: dict) -> dict:
    """Send payload to Navigator Core API (or mock)."""
    from core_client.api import NavigatorCoreClient

    client = NavigatorCoreClient(
        base_url=settings.core_api_url,
        api_token=settings.core_api_token,
    )

    response = await client.import_organizer(payload)
    logger.info(
        "Core API response: status=%s, assigned_status=%s, mock=%s",
        response.get("status"),
        response.get("assigned_status"),
        response.get("_mock", False),
    )
    return {**response, "_core_metrics": client.get_metrics()}


async def run_event_harvest(url: str) -> dict:
    """Discover and classify events from an organization's /news, /afisha pages."""
    from processors.deepseek_client import DeepSeekClient
    from processors.event_processor import EventProcessor, to_event_payload
    from prompts.schemas import EntityType, HarvestInput
    from strategies.event_discovery import EventDiscoverer

    discoverer = EventDiscoverer(max_event_pages=3, max_events_per_page=10)
    discovery = await discoverer.discover_events(url)

    if not discovery.candidates:
        return {
            "url": url,
            "status": "no_events",
            "event_pages_found": discovery.event_pages_found,
            "errors": discovery.errors,
        }

    client = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model_name,
    )
    processor = EventProcessor(deepseek_client=client)

    events: list[dict] = []
    for candidate in discovery.candidates:
        try:
            harvest_input = HarvestInput(
                source_id="cli-event-harvest",
                source_item_id=f"{url}#{candidate.title[:50]}",
                entity_type=EntityType.EVENT,
                raw_text=candidate.markdown[:15000],
                source_url=candidate.url,
                source_kind="org_website",
            )
            result = processor.process(harvest_input)
            payload = to_event_payload(result)
            payload["_discovery"] = {
                "discovered_from": candidate.discovered_from,
                "freshness_days": candidate.freshness_days,
                "original_title": candidate.title,
            }
            events.append(payload)
        except Exception as e:
            events.append({
                "error": str(e),
                "candidate_title": candidate.title,
                "candidate_url": candidate.url,
            })

    return {
        "url": url,
        "status": "success",
        "event_pages_found": discovery.event_pages_found,
        "candidates_found": len(discovery.candidates),
        "events_classified": len([e for e in events if "error" not in e]),
        "events": events,
        "llm_metrics": client.get_metrics(),
        "errors": discovery.errors,
    }


async def crawl_firecrawl(url: str) -> tuple[str, dict]:
    """Crawl URL via Firecrawl Cloud API, return (markdown, meta)."""
    from strategies.firecrawl_strategy import FirecrawlClient

    client = FirecrawlClient()
    if not client.enabled:
        raise RuntimeError("FIRECRAWL_API_KEY not set")

    result = await client.scrape(url)
    if not result.success:
        raise RuntimeError(f"Firecrawl failed: {result.error}")

    meta = {"crawl_engine": "firecrawl", "pages_attempted": 1, "pages_success": 1}
    return result.markdown, meta


async def crawl_multi_page(url: str) -> tuple[str, dict]:
    """Crawl URL + subpages via MultiPageCrawler, return (markdown, meta)."""
    from strategies.multi_page import MultiPageCrawler

    crawler = MultiPageCrawler(max_subpages=5)
    result = await crawler.crawl_organization(url)

    if not result.success:
        raise RuntimeError(
            f"Multi-page crawl failed: {result.total_pages_success}/{result.total_pages_attempted} pages"
        )

    meta = {
        "pages_attempted": result.total_pages_attempted,
        "pages_success": result.total_pages_success,
        "page_urls": [p.url for p in result.pages if p.success],
    }
    return result.merged_markdown, meta


async def run(
    url: str,
    crawl_only: bool = False,
    enrich_geo: bool = False,
    to_core: bool = False,
    multi_page: bool = False,
    save_raw_path: str | None = None,
    site_extract: bool = False,
    use_firecrawl: bool = False,
) -> dict:
    """Full pipeline: crawl → [site-extract] → classify → [Dadata] → [Core API].

    Uses harvest.run_organization_harvest when not use_firecrawl and not crawl_only.
    """
    from strategies.site_extractors import SiteExtractorRegistry

    if use_firecrawl:
        crawl_meta = {}
        try:
            markdown, crawl_meta = await crawl_firecrawl(url)
        except Exception as e:
            return {"error": f"Crawl failed: {e}", "url": url}
        if not markdown.strip():
            return {"error": "Empty markdown after crawl", "url": url}
        site_data = SiteExtractorRegistry.extract_if_known(url, markdown)
        if crawl_only:
            return {"url": url, "status": "crawl_only", "markdown_length": len(markdown), "preview": markdown[:500], **crawl_meta, **({"site_extraction": site_data} if site_data else {})}
        if site_extract and site_data:
            return {"url": url, "status": "site_extract_only", "platform": site_data.get("platform"), "site_extraction": site_data, "markdown_length": len(markdown)}
        try:
            result, classify_elapsed, deepseek_client = classify(url, markdown)
        except Exception as e:
            return {"error": f"Classification failed: {e}", "url": url}
        geo_results = None
        if enrich_geo or to_core:
            try:
                geo_results = await enrich_venues(result) or None
            except Exception as e:
                logger.error("Dadata enrichment failed: %s", e)
        from processors.organization_processor import to_core_import_payload

        payload = to_core_import_payload(result, geo_results=geo_results)
        if site_data:
            payload["_site_extraction"] = site_data
        payload["_meta"] = {
            "url": url, "multi_page": multi_page, "site_platform": site_data.get("platform") if site_data else None,
            "elapsed_classify_s": round(classify_elapsed, 1), "ai_decision": result.ai_metadata.decision,
            "ai_confidence": result.ai_metadata.ai_confidence_score, "works_with_elderly": result.ai_metadata.works_with_elderly,
            "venues_geocoded": sum(1 for g in (geo_results or []) if g.fias_id), **crawl_meta, **deepseek_client.get_metrics(),
        }
        if to_core:
            try:
                payload["_core_response"] = await send_to_core(payload)
            except Exception as e:
                payload["_core_error"] = str(e)
        return payload

    if crawl_only:
        try:
            if multi_page:
                markdown, crawl_meta = await crawl_multi_page(url)
            else:
                markdown = await crawl(url, save_raw_path=save_raw_path)
                crawl_meta = {}
        except Exception as e:
            return {"error": f"Crawl failed: {e}", "url": url}
        if not markdown.strip():
            return {"error": "Empty markdown after crawl", "url": url}
        site_data = SiteExtractorRegistry.extract_if_known(url, markdown)
        return {"url": url, "status": "crawl_only", "markdown_length": len(markdown), "preview": markdown[:500], **crawl_meta, **({"site_extraction": site_data} if site_data else {})}

    from harvest.run_organization_harvest import run_organization_harvest

    out = await run_organization_harvest(
        url,
        source_id="cli-single-url",
        source_item_id=url,
        existing_entity_id=None,
        multi_page=multi_page,
        enrich_geo=enrich_geo or to_core,
        additional_context="",
        source_kind="org_website",
        try_site_extractor=True,
        deepseek_client=None,
    )

    if not out["success"]:
        return {"error": out.get("error", "harvest failed"), "url": url}

    result = out["result"]
    payload = out["payload"]
    crawl_meta = out["crawl_meta"]
    geo_results = out.get("geo_results")
    llm_metrics = out.get("llm_metrics", {})
    site_data = out.get("site_extraction")

    if site_data:
        payload["_site_extraction"] = site_data
    payload["_meta"] = {
        "url": url,
        "multi_page": multi_page,
        "site_platform": site_data.get("platform") if site_data else None,
        "ai_decision": result.ai_metadata.decision,
        "ai_confidence": result.ai_metadata.ai_confidence_score,
        "works_with_elderly": result.ai_metadata.works_with_elderly,
        "venues_geocoded": sum(1 for g in (geo_results or []) if g.fias_id),
        **crawl_meta,
        **llm_metrics,
    }

    if to_core:
        try:
            core_response = await send_to_core(payload)
            payload["_core_response"] = core_response
        except Exception as e:
            payload["_core_error"] = str(e)

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crawl one URL → classify → [Dadata] → [Core API]"
    )
    parser.add_argument("url", nargs="?", help="Page URL to crawl")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument("--check-env", action="store_true", help="Check env vars and exit")
    parser.add_argument("--crawl-only", action="store_true", help="Only crawl, skip LLM")
    parser.add_argument("--enrich-geo", action="store_true", help="Geocode venues via Dadata")
    parser.add_argument("--to-core", action="store_true", help="Send payload to Core API (implies --enrich-geo)")
    parser.add_argument("--multi-page", action="store_true", help="Crawl main page + subpages (/kontakty, /o-nas, /uslugi)")
    parser.add_argument("--save-raw", metavar="DIR", help="Save raw markdown/HTML to DIR")
    parser.add_argument("--site-extract", action="store_true", help="Extract via site-specific template (0 tokens), skip LLM if platform known")
    parser.add_argument("--firecrawl", action="store_true", help="Use Firecrawl Cloud instead of Crawl4AI (requires FIRECRAWL_API_KEY)")
    parser.add_argument("--harvest-events", action="store_true", help="Discover and classify events from /news, /afisha pages")
    args = parser.parse_args()

    if args.check_env:
        checks = {
            "DEEPSEEK_API_KEY": settings.deepseek_api_key,
            "DADATA_API_KEY": settings.dadata_api_key,
            "CORE_API_URL": settings.core_api_url,
            "CORE_API_TOKEN": settings.core_api_token,
        }
        all_ok = True
        for name, val in checks.items():
            is_placeholder = not val or "your" in val.lower()
            status = f"SET (len={len(val)})" if not is_placeholder else "MISSING/placeholder"
            print(f"  {name}: {status}")
            if name == "DEEPSEEK_API_KEY" and is_placeholder:
                all_ok = False
        return 0 if all_ok else 1

    if not args.url:
        parser.error("url is required (unless using --check-env)")

    if args.harvest_events:
        out = asyncio.run(run_event_harvest(args.url))
    else:
        out = asyncio.run(run(
            args.url,
            crawl_only=args.crawl_only,
            enrich_geo=args.enrich_geo,
            to_core=args.to_core,
            multi_page=args.multi_page,
            save_raw_path=args.save_raw,
            site_extract=args.site_extract,
            use_firecrawl=args.firecrawl,
        ))
    print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if "error" not in out else 1


if __name__ == "__main__":
    sys.exit(main())
