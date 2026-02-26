#!/usr/bin/env python3
"""CLI for Silver Age (silveragemap.ru) scraper pipeline.

Usage:
    # Scrape first 2 pages of practices (analysis only)
    python -m scripts.run_silverage_import --analyze --max-pages 2

    # Dry-run: scrape 5 practices + events, show what would be imported
    python -m scripts.run_silverage_import --max-practices 5 --dry-run

    # Import first 10 organizations (with website discovery + harvest)
    python -m scripts.run_silverage_import --max-practices 20 --limit-orgs 10

    # Full import with caching and output
    python -m scripts.run_silverage_import --cache-dir data/silverage/cache --output data/silverage/results.json

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
        "--output", "-o",
        type=str,
        default=None,
        help="Save results JSON to this path",
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
    from aggregators.silverage.silverage_pipeline import SilverAgePipeline

    pipeline = SilverAgePipeline(
        scrape_delay=args.scrape_delay,
        cache_dir=args.cache_dir,
    )
    report = await pipeline.run(
        max_pages=args.max_pages,
        max_practices=args.max_practices,
        limit_orgs=args.limit_orgs,
        dry_run=args.dry_run,
        scrape_events=not args.no_events,
        output_path=args.output,
    )

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

    if args.output:
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
