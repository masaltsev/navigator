#!/usr/bin/env python3
"""
CLI: crawl one URL with Crawl4AI, classify via OrganizationProcessor + DeepSeek.

Usage:
  cd ai-pipeline/harvester && python -m scripts.run_single_url https://example.com
  python -m scripts.run_single_url https://example.com --pretty --save-raw /tmp/debug
  python -m scripts.run_single_url --crawl-only https://example.com   # skip LLM
  python -m scripts.run_single_url --check-env
"""
import argparse
import asyncio
import json
import logging
import os
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

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("run_single_url")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)


async def crawl(url: str, save_raw_path: str | None = None) -> str:
    """Crawl URL, return markdown text (no LLM)."""
    browser_config = BrowserConfig(
        headless=os.getenv("CRAWL4AI_HEADLESS", "true").lower() == "true",
        enable_stealth=True,
        user_agent=os.getenv("CRAWL4AI_USER_AGENT", _USER_AGENT),
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


def classify(url: str, markdown: str) -> dict:
    """Classify markdown via OrganizationProcessor → DeepSeek."""
    from processors.deepseek_client import DeepSeekClient
    from processors.organization_processor import OrganizationProcessor, to_core_import_payload
    from prompts.schemas import EntityType, HarvestInput

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    client = DeepSeekClient(api_key=api_key)
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

    payload = to_core_import_payload(result)
    payload["_meta"] = {
        "elapsed_s": round(elapsed, 1),
        "ai_decision": result.ai_metadata.decision,
        "ai_confidence": result.ai_metadata.ai_confidence_score,
        "works_with_elderly": result.ai_metadata.works_with_elderly,
        **client.get_metrics(),
    }
    return payload


async def run(url: str, crawl_only: bool = False, save_raw_path: str | None = None) -> dict:
    """Full pipeline: crawl → classify."""
    try:
        markdown = await crawl(url, save_raw_path=save_raw_path)
    except Exception as e:
        return {"error": f"Crawl failed: {e}", "url": url}

    if not markdown.strip():
        return {"error": "Empty markdown after crawl", "url": url}

    if crawl_only:
        return {
            "url": url,
            "status": "crawl_only",
            "markdown_length": len(markdown),
            "preview": markdown[:500],
        }

    try:
        return classify(url, markdown)
    except Exception as e:
        return {"error": f"Classification failed: {e}", "url": url}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crawl one URL, classify via OrganizationProcessor + DeepSeek"
    )
    parser.add_argument("url", nargs="?", help="Page URL to crawl")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument("--check-env", action="store_true", help="Check DEEPSEEK_API_KEY and exit")
    parser.add_argument("--crawl-only", action="store_true", help="Only crawl, skip LLM classification")
    parser.add_argument("--save-raw", metavar="DIR", help="Save raw markdown/HTML to DIR")
    args = parser.parse_args()

    if args.check_env:
        key = os.getenv("DEEPSEEK_API_KEY", "")
        if not key or key.startswith("sk-your") or "your-key" in key.lower():
            print("DEEPSEEK_API_KEY is missing or placeholder.", file=sys.stderr)
            return 1
        print("DEEPSEEK_API_KEY is set (length = %d)." % len(key))
        return 0

    if not args.url:
        parser.error("url is required (unless using --check-env)")

    out = asyncio.run(run(args.url, crawl_only=args.crawl_only, save_raw_path=args.save_raw))
    print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if "error" not in out else 1


if __name__ == "__main__":
    sys.exit(main())
