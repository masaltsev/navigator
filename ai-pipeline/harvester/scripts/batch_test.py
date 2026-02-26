#!/usr/bin/env python3
"""
Sprint 3.6 batch test: process N URLs via the full pipeline.

Runs directly (asyncio, no Celery) for test observability.
Saves HTML/markdown snapshots for KCSON and medical sites.

Usage:
    cd ai-pipeline/harvester
    python -m scripts.batch_test --urls-json scripts/batch_urls.json --save-raw tests/fixtures/batch_raw --pretty
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

configure_logging()
settings = get_settings()
logger = structlog.get_logger("batch_test")


async def process_single(
    url: str,
    source_id: str,
    multi_page: bool,
    save_raw_dir: Path | None,
    enrich_geo: bool,
    to_core: bool,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Process a single URL through the full pipeline."""
    from core_client.api import NavigatorCoreClient
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
    from enrichment.dadata_client import DadataClient
    from processors.deepseek_client import DeepSeekClient
    from processors.organization_processor import OrganizationProcessor, to_core_import_payload
    from prompts.schemas import EntityType, HarvestInput
    from strategies.multi_page import MultiPageCrawler

    async with semaphore:
        t0 = time.time()
        crawl_meta: dict = {}

        try:
            if multi_page:
                crawler = MultiPageCrawler(max_subpages=4, crawl_delay=0.5)
                multi_result = await crawler.crawl_organization(url)
                if not multi_result.success:
                    return {"url": url, "status": "error", "error": "crawl_failed", "elapsed_s": round(time.time() - t0, 1)}
                markdown = multi_result.merged_markdown
                crawl_meta = {
                    "pages_attempted": multi_result.total_pages_attempted,
                    "pages_success": multi_result.total_pages_success,
                    "page_urls": [p.url for p in multi_result.pages if p.success],
                }

                if save_raw_dir:
                    safe = url.replace("https://", "").replace("http://", "").rstrip("/").replace("/", "_")[:60]
                    save_raw_dir.mkdir(parents=True, exist_ok=True)
                    md_path = save_raw_dir / f"{safe}_merged.txt"
                    md_path.write_text(markdown[:100000], encoding="utf-8")

                    for page in multi_result.pages:
                        if page.success and page.markdown:
                            page_safe = page.url.replace("https://", "").replace("http://", "").rstrip("/").replace("/", "_")[:60]
                            (save_raw_dir / f"{page_safe}_page.txt").write_text(page.markdown[:100000], encoding="utf-8")
            else:
                browser_config = BrowserConfig(
                    headless=settings.crawl4ai_headless,
                    enable_stealth=True,
                    user_agent=settings.crawl4ai_user_agent,
                )
                run_config = CrawlerRunConfig(
                    word_count_threshold=0, page_timeout=30000,
                    wait_until="domcontentloaded", delay_before_return_html=2.0,
                    magic=True, simulate_user=True, cache_mode=CacheMode.BYPASS,
                )
                async with AsyncWebCrawler(config=browser_config) as c:
                    res = await c.arun(url=url, config=run_config)
                if not res.success:
                    return {"url": url, "status": "error", "error": "crawl_failed", "elapsed_s": round(time.time() - t0, 1)}
                markdown = res.markdown or res.fit_markdown or ""

                if save_raw_dir:
                    safe = url.replace("https://", "").replace("http://", "").rstrip("/").replace("/", "_")[:60]
                    save_raw_dir.mkdir(parents=True, exist_ok=True)
                    (save_raw_dir / f"{safe}_markdown.txt").write_text(markdown[:100000], encoding="utf-8")
                    html = getattr(res, "cleaned_html", "") or getattr(res, "raw_html", "") or ""
                    if html:
                        (save_raw_dir / f"{safe}_html.html").write_text(html[:200000], encoding="utf-8")

            if not markdown.strip():
                return {"url": url, "status": "error", "error": "empty_markdown", "elapsed_s": round(time.time() - t0, 1)}

            t_crawl = time.time()

        except Exception as e:
            return {"url": url, "status": "error", "error": f"crawl: {e}", "elapsed_s": round(time.time() - t0, 1)}

        try:
            client = DeepSeekClient(
                api_key=settings.deepseek_api_key,
                model=settings.deepseek_model_name,
            )
            processor = OrganizationProcessor(deepseek_client=client)

            harvest_input = HarvestInput(
                source_id=source_id,
                source_item_id=url,
                entity_type=EntityType.ORGANIZATION,
                raw_text=markdown[:30000],
                source_url=url,
                source_kind="org_website",
            )

            result = processor.process(harvest_input)
            t_classify = time.time()

            geo_results = None
            if enrich_geo:
                dadata = DadataClient(
                    api_key=settings.dadata_api_key,
                    secret_key=settings.dadata_secret_key,
                    use_clean=settings.dadata_use_clean,
                )
                if dadata.enabled and result.venues:
                    addresses = [v.address_raw for v in result.venues]
                    geo_results = await dadata.geocode_batch(addresses)

            payload = to_core_import_payload(result, geo_results=geo_results)
            t_enrich = time.time()

            core_response = None
            if to_core:
                core_client = NavigatorCoreClient(
                    base_url=settings.core_api_url,
                    api_token=settings.core_api_token,
                )
                try:
                    core_response = await core_client.import_organizer(payload)
                except Exception as e:
                    core_response = {"error": str(e)}

            t_end = time.time()
            llm_metrics = client.get_metrics()

            return {
                "url": url,
                "status": "success",
                "title": result.title,
                "decision": result.ai_metadata.decision,
                "confidence": result.ai_metadata.ai_confidence_score,
                "works_with_elderly": result.ai_metadata.works_with_elderly,
                "venues_count": len(result.venues),
                "venues_geocoded": sum(1 for g in (geo_results or []) if g.fias_id) if geo_results else 0,
                "services_count": len(result.classification.service_codes),
                "org_types": result.classification.organization_type_codes,
                "ownership_type": result.classification.ownership_type_code,
                "core_status": core_response.get("assigned_status") if core_response else None,
                "timing": {
                    "crawl_s": round(t_crawl - t0, 1),
                    "classify_s": round(t_classify - t_crawl, 1),
                    "enrich_s": round(t_enrich - t_classify, 1),
                    "total_s": round(t_end - t0, 1),
                },
                "llm_metrics": llm_metrics,
                **crawl_meta,
            }

        except Exception as e:
            return {
                "url": url,
                "status": "error",
                "error": f"classify: {e}",
                "elapsed_s": round(time.time() - t0, 1),
                **crawl_meta,
            }


async def run_batch(
    urls: list[dict],
    concurrency: int = 2,
    multi_page: bool = True,
    save_raw_dir: Path | None = None,
    enrich_geo: bool = True,
    to_core: bool = False,
) -> list[dict]:
    """Run batch of URLs through the pipeline with limited concurrency."""
    semaphore = asyncio.Semaphore(concurrency)
    tasks = []

    for item in urls:
        url = item["url"]
        source_id = item.get("source_id", "batch-test")
        tasks.append(
            process_single(
                url=url,
                source_id=source_id,
                multi_page=multi_page,
                save_raw_dir=save_raw_dir,
                enrich_geo=enrich_geo,
                to_core=to_core,
                semaphore=semaphore,
            )
        )

    results = []
    total = len(tasks)
    completed = 0

    for coro in asyncio.as_completed(tasks):
        result = await coro
        completed += 1
        status = result.get("status", "?")
        title = result.get("title", result.get("error", "?"))[:50]
        logger.info(
            "[%d/%d] %s — %s: %s",
            completed, total, result["url"][:50], status, title,
        )
        results.append(result)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch test: process URLs through full pipeline")
    parser.add_argument("--urls-json", required=True, help="JSON file with list of {url, source_id}")
    parser.add_argument("--concurrency", type=int, default=2, help="Max concurrent crawls (default 2)")
    parser.add_argument("--multi-page", action="store_true", default=True, help="Use multi-page crawl")
    parser.add_argument("--no-multi-page", action="store_true", help="Disable multi-page crawl")
    parser.add_argument("--save-raw", metavar="DIR", help="Save markdown/HTML snapshots to DIR")
    parser.add_argument("--enrich-geo", action="store_true", default=True, help="Enrich with Dadata")
    parser.add_argument("--no-geo", action="store_true", help="Skip Dadata enrichment")
    parser.add_argument("--to-core", action="store_true", help="Send to Core API")
    parser.add_argument("--output", metavar="FILE", help="Save results to JSON file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    with open(args.urls_json, "r", encoding="utf-8") as f:
        urls = json.load(f)

    logger.info("Loaded %d URLs from %s", len(urls), args.urls_json)

    multi_page = not args.no_multi_page
    enrich_geo = not args.no_geo

    save_raw_dir = Path(args.save_raw) if args.save_raw else None

    t_start = time.time()
    results = asyncio.run(
        run_batch(
            urls=urls,
            concurrency=args.concurrency,
            multi_page=multi_page,
            save_raw_dir=save_raw_dir,
            enrich_geo=enrich_geo,
            to_core=args.to_core,
        )
    )
    t_total = time.time() - t_start

    success = [r for r in results if r.get("status") == "success"]
    errors = [r for r in results if r.get("status") == "error"]

    accepted = [r for r in success if r.get("decision") == "accepted"]
    rejected = [r for r in success if r.get("decision") == "rejected"]
    needs_review = [r for r in success if r.get("decision") == "needs_review"]

    summary = {
        "total": len(results),
        "success": len(success),
        "errors": len(errors),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "needs_review": len(needs_review),
        "works_with_elderly": sum(1 for r in success if r.get("works_with_elderly")),
        "avg_confidence": round(sum(r.get("confidence", 0) for r in success) / max(len(success), 1), 3),
        "total_time_s": round(t_total, 1),
        "avg_time_per_url_s": round(t_total / max(len(results), 1), 1),
        "error_urls": [r["url"] for r in errors],
    }

    output = {
        "summary": summary,
        "results": results,
    }

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info("Results saved to %s", args.output)

    print("\n" + "=" * 60)
    print("BATCH TEST SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("=" * 60)

    if args.pretty:
        print("\nFull results:")
        print(json.dumps(output, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
