#!/usr/bin/env python3
"""
CLI: crawl one URL with Crawl4AI + DeepSeek, output RawOrganizationData as JSON.
Usage (from repo root):
  cd ai-pipeline/harvester && python -m scripts.run_single_url https://example.com
Or with PYTHONPATH:
  PYTHONPATH=ai-pipeline/harvester python ai-pipeline/harvester/scripts/run_single_url.py https://example.com
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure harvester root is on path when run as script
_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))

# Load .env so DEEPSEEK_API_KEY etc. are available to os.getenv()
_env_file = _harvester_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode
from strategies.strategy_router import StrategyRouter
from schemas.extraction import RawOrganizationData


def _parse_profile_config() -> dict:
    return {}


async def run(url: str, save_raw_path: str | None = None) -> dict:
    router = StrategyRouter()
    config = router.get_extraction_config("org_website", _parse_profile_config())
    config = config.clone(cache_mode=CacheMode.BYPASS)

    user_agent = os.getenv(
        "CRAWL4AI_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    )
    browser_config = BrowserConfig(
        headless=os.getenv("CRAWL4AI_HEADLESS", "true").lower() == "true",
        enable_stealth=True,
        user_agent=user_agent,
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=config)

    if save_raw_path:
        raw_dir = Path(save_raw_path)
        raw_dir.mkdir(parents=True, exist_ok=True)
        safe_name = url.replace("https://", "").replace("http://", "").rstrip("/").replace("/", "_")[:80]
        for name, content in (
            ("markdown.txt", getattr(result, "markdown", None) or getattr(result, "fit_markdown", "") or ""),
            ("cleaned_html.html", getattr(result, "cleaned_html", None) or getattr(result, "raw_html", "") or ""),
        ):
            if content:
                (raw_dir / f"{safe_name}_{name}").write_text(content if isinstance(content, str) else str(content), encoding="utf-8")
        if save_raw_path:
            print("Raw content saved to", raw_dir, file=sys.stderr)

    if not result.success:
        return {"error": result.error_message or "unknown", "url": url}

    raw = result.extracted_content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON from extractor", "url": url, "raw_preview": raw[:500]}

    # Crawl4AI/LLM may return a list of one or more items; we expect one organization
    if isinstance(data, list):
        if not data:
            return {"error": "Extractor returned empty list", "url": url}
        data = data[0]
    if not isinstance(data, dict):
        return {"error": "Extractor did not return object or list", "url": url, "raw": data}

    # Validate and normalize with Pydantic
    try:
        model = RawOrganizationData(**data)
        return model.model_dump(mode="json")
    except Exception as e:
        return {"error": str(e), "url": url, "raw": data}


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl one URL, output RawOrganizationData JSON")
    parser.add_argument("url", nargs="?", help="Page URL to crawl (optional with --check-env)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    parser.add_argument("--check-env", action="store_true", help="Only check that DEEPSEEK_API_KEY is set, then exit")
    parser.add_argument("--save-raw", metavar="DIR", help="Save raw markdown/HTML to DIR for debugging")
    args = parser.parse_args()

    if args.check_env:
        key = os.getenv("DEEPSEEK_API_KEY", "")
        if not key or key.startswith("sk-your") or "your-key" in key.lower():
            print("DEEPSEEK_API_KEY is missing or placeholder. Set it in .env or environment.", file=sys.stderr)
            return 1
        print("DEEPSEEK_API_KEY is set (length = %d)." % len(key))
        return 0

    if not args.url:
        parser.error("url is required (unless using --check-env)")
    out = asyncio.run(run(args.url, save_raw_path=args.save_raw))
    print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if "error" not in out else 1


if __name__ == "__main__":
    sys.exit(main())
