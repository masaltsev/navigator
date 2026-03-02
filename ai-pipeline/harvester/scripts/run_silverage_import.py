#!/usr/bin/env python3
"""CLI for Silver Age (silveragemap.ru) scraper pipeline.

Usage:
    # Scrape first 2 pages of practices (analysis only)
    python -m scripts.run_silverage_import --analyze --max-pages 2

    # Dry-run: scrape 5 practices + events, show what would be imported
    python -m scripts.run_silverage_import --max-practices 5 --dry-run

    # Import first 10 organizations; save run to data/runs/2026-02-27_silverage/
    python -m scripts.run_silverage_import --max-practices 20 --limit-orgs 10 --run-id 2026-02-27_silverage

    # Full import with run trace (run_config.json, progress.jsonl, run_summary.json, report.json)
    python -m scripts.run_silverage_import --cache-dir data/silverage/cache --run-id 2026-02-27_silverage

    # Legacy: single output file
    python -m scripts.run_silverage_import --max-practices 5 --output data/silverage/results.json

    # Skip events
    python -m scripts.run_silverage_import --max-pages 3 --no-events --dry-run
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Silver Age (silveragemap.ru) pipeline for Navigator Harvester"
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--analyze",
        action="store_true",
        help="Scrape and analyze only: show statistics without importing",
    )
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without sending to Core",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max practice list pages to scrape (each has ~16 practices, 65 total)",
    )
    parser.add_argument(
        "--max-practices",
        type=int,
        default=None,
        help="Max practice detail pages to scrape",
    )
    parser.add_argument(
        "--limit-orgs",
        type=int,
        default=None,
        help="Max organizations to process (after grouping)",
    )
    parser.add_argument(
        "--no-events",
        action="store_true",
        help="Skip events scraping",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Directory for caching scraped pages (avoids re-fetching)",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run identifier: write to data/runs/<run_id>/ (run_config.json, progress.jsonl, run_summary.json, report.json)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Save results JSON to this path (legacy; use --run-id to write to data/runs/)",
    )
    parser.add_argument(
        "--scrape-delay",
        type=float,
        default=1.5,
        help="Delay between HTTP requests (seconds, default 1.5)",
    )

    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    from config.logging import configure_logging
    configure_logging()

    if args.analyze:
        await _run_analyze(args)
    else:
        await _run_pipeline(args)


async def _run_analyze(args: argparse.Namespace) -> None:
    from aggregators.silverage.silverage_pipeline import SilverAgePipeline, group_practices_by_org

    pipeline = SilverAgePipeline(
        scrape_delay=args.scrape_delay,
        cache_dir=args.cache_dir,
    )
    practices, organizations = await pipeline.scrape_only(
        max_pages=args.max_pages,
        max_practices=args.max_practices,
    )

    print()
    print("=== Silver Age Analysis ===")
    print(f"Practices scraped: {len(practices)}")
    print(f"Unique organizations: {len(organizations)}")
    print()

    all_cats: dict[str, int] = {}
    for p in practices:
        for c in p.categories:
            all_cats[c] = all_cats.get(c, 0) + 1
    print("Categories:")
    for cat, count in sorted(all_cats.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")

    all_regions: dict[str, int] = {}
    for p in practices:
        if p.region:
            all_regions[p.region] = all_regions.get(p.region, 0) + 1
    print(f"\nRegions: {len(all_regions)} unique")
    for reg, count in sorted(all_regions.items(), key=lambda x: -x[1])[:15]:
        print(f"  {reg}: {count}")

    with_email = sum(1 for o in organizations if o.email)
    with_website = sum(1 for o in organizations if o.website)
    with_vk = sum(1 for o in organizations if o.vk_url)
    print(f"\nOrganization contacts:")
    print(f"  With email: {with_email}/{len(organizations)}")
    print(f"  With website: {with_website}/{len(organizations)}")
    print(f"  With VK: {with_vk}/{len(organizations)}")

    print(f"\nTop organizations by practice count:")
    for o in organizations[:10]:
        print(f"  [{o.practice_count}] {o.name[:70]} ({o.region})")


async def _run_pipeline(args: argparse.Namespace) -> None:
    import time
    from scripts.aggregator_run_writer import (
        run_dir_path,
        write_run_config,
        append_progress,
        write_run_summary,
        silverage_report_to_progress_entries,
    )

    from aggregators.silverage.silverage_pipeline import SilverAgePipeline

    run_dir = run_dir_path(args.run_id) if args.run_id else None
    output_path = None
    if run_dir:
        run_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(run_dir / "report.json")
        config = {k: getattr(args, k, None) for k in ["max_pages", "max_practices", "limit_orgs", "no_events", "cache_dir", "scrape_delay", "dry_run"]}
        write_run_config(run_dir, args.run_id, config)
    elif args.output:
        output_path = args.output

    pipeline = SilverAgePipeline(
        scrape_delay=args.scrape_delay,
        cache_dir=args.cache_dir,
    )
    t0 = time.monotonic()
    report = await pipeline.run(
        max_pages=args.max_pages,
        max_practices=args.max_practices,
        limit_orgs=args.limit_orgs,
        dry_run=args.dry_run,
        scrape_events=not args.no_events,
        output_path=output_path,
    )
    elapsed = time.monotonic() - t0

    if run_dir:
        for entry in silverage_report_to_progress_entries(report):
            append_progress(run_dir, entry)
        counters = {
            "orgs_created": report.orgs_created,
            "orgs_matched": report.orgs_matched,
            "orgs_errors": report.orgs_errors,
            "total_orgs": len(report.org_results),
            "total_events": len(report.event_results),
            "total_practices": report.total_practices,
            "unique_organizations": report.unique_organizations,
        }
        write_run_summary(run_dir, counters, elapsed_sec=elapsed)
        print(f"\nRun trace saved to {run_dir}")

    print()
    print(report.summary())

    if args.dry_run and report.org_results:
        print()
        print("=== Dry-run org results (first 20) ===")
        for r in report.org_results[:20]:
            website = r.discovered_website or "no website"
            print(f"  [{r.practice_count}] {r.name[:60]}")
            print(f"             Region: {r.region} | Website: {website}")

    if args.dry_run and report.event_results:
        print()
        print("=== Dry-run event results ===")
        for r in report.event_results[:20]:
            print(f"  {r.date_text} | {r.title[:60]}")
            print(f"             {r.location} | {r.page_url}")

    if args.output and not run_dir:
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
