#!/usr/bin/env python3
"""
Dry re-run of enrichment for a random sample from reject.json to test whether
rejects were due to Playwright/Chromium errors (first pass) vs real no-match.

No DB writes: only search + verify (enrich_missing_source), no source creation or import.

For reliable crawl (no "unable to open database file") run from your terminal
with Playwright Chromium installed in project dir (see README / setup_environment.sh).

Usage:
  cd ai-pipeline/harvester
  python -m scripts.reject_redry data/runs/2026-02-25_no_sources/reject.json --n 10
  python -m scripts.reject_redry data/runs/2026-02-25_no_sources/reject.json --n 10 --seed 42
"""

import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))

_browser_tmp = _harvester_root / "data" / "browser_profile"
_playwright_browsers = _harvester_root / "data" / "playwright_browsers"
_browser_tmp.mkdir(parents=True, exist_ok=True)
_playwright_browsers.mkdir(parents=True, exist_ok=True)
os.environ["TMPDIR"] = os.environ["TMP"] = os.environ["TEMP"] = str(_browser_tmp)
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_playwright_browsers)

_env_file = _harvester_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry re-run enrichment for random sample from reject.json")
    parser.add_argument("reject_json", help="Path to reject.json (e.g. data/runs/2026-02-25_no_sources/reject.json)")
    parser.add_argument("--n", type=int, default=10, help="Number of random orgs to try (default 10)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    path = Path(args.reject_json)
    if not path.is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print("Error: JSON must be an array of objects", file=sys.stderr)
        sys.exit(1)

    # Each row: org_id, org_title (required for enrich_missing_source)
    rows = [r for r in data if isinstance(r, dict) and r.get("org_title")]
    if len(rows) < args.n:
        print(f"Warning: only {len(rows)} rows with org_title, using all", file=sys.stderr)
        sample = rows
    else:
        rng = random.Random(args.seed)
        sample = rng.sample(rows, args.n)

    from config.logging import configure_logging
    from config.settings import get_settings
    from processors.deepseek_client import DeepSeekClient
    from search.enrichment_pipeline import EnrichmentPipeline
    from search.provider import get_search_provider

    configure_logging()
    settings = get_settings()
    provider = get_search_provider()
    if not provider:
        print("ERROR: No search provider (set SEARCH_PROVIDER and/or Yandex/DDG keys)", file=sys.stderr)
        sys.exit(1)

    llm = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model_name,
    )
    pipeline = EnrichmentPipeline(provider, llm)

    print("DRY RUN: no DB writes. Re-running search + verify for random reject sample.")
    print(f"Reject file: {path} | Sample: {len(sample)} orgs")
    if args.seed is not None:
        print(f"Seed: {args.seed}")
    print()

    async def run_one(idx: int, row: dict) -> dict:
        org_title = row.get("org_title", "")
        org_id = row.get("org_id", "")
        result = await pipeline.enrich_missing_source(
            org_title,
            city="",
            inn="",
            source_id="",
            additional_context="",
            source_kind="org_website",
        )
        crawl_errors = [getattr(v, "crawl_error", None) for v in result.all_verifications if getattr(v, "crawl_error", None)]
        return {
            "idx": idx + 1,
            "org_id": org_id,
            "org_title": org_title[:50],
            "tier": result.tier.value,
            "verified_url": result.verified_url or "",
            "crawl_errors": crawl_errors,
            "verifications": len(result.all_verifications),
        }

    async def run_all() -> None:
        results = []
        for i, row in enumerate(sample):
            r = await run_one(i, row)
            results.append(r)
            err_summary = "crawl_error" if r["crawl_errors"] else "ok"
            print(f"[{r['idx']}/{len(sample)}] {r['org_title']!r} -> tier={r['tier']} verified={bool(r['verified_url'])} {err_summary}")

        # Summary
        auto = sum(1 for r in results if r["tier"] == "auto")
        review = sum(1 for r in results if r["tier"] == "review")
        reject = sum(1 for r in results if r["tier"] == "reject")
        with_crawl_error = sum(1 for r in results if r["crawl_errors"])
        print()
        print("--- Summary ---")
        print(f"  AUTO: {auto}  REVIEW: {review}  REJECT: {reject}")
        print(f"  With crawl_error (this run): {with_crawl_error}")
        if reject > 0 and with_crawl_error == 0:
            print("  → No crawl errors in this sample; rejects are likely LLM/search, not browser.")
        elif with_crawl_error > 0:
            print("  → Some crawl errors; hypothesis (browser caused first-pass rejects) still possible.")

    asyncio.run(run_all())


if __name__ == "__main__":
    main()
