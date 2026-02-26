#!/usr/bin/env python3
"""CLI for SONKO (Socially Oriented NCOs) registry pipeline.

Usage:
    # Download XLSX from data.economy.gov.ru
    python -m scripts.run_sonko_import --download

    # Analyze: stats by OKVED, name keywords, combined
    python -m scripts.run_sonko_import --analyze --xlsx data/sonko/sonko_organizations.xlsx

    # Dry-run (first 20 orgs)
    python -m scripts.run_sonko_import --xlsx data/sonko/sonko_organizations.xlsx --limit 20 --dry-run

    # Import with full harvest
    python -m scripts.run_sonko_import --xlsx data/sonko/sonko_organizations.xlsx --limit 50

    # Include broader OKVED codes (86, 93, 96)
    python -m scripts.run_sonko_import --xlsx data/sonko/sonko_organizations.xlsx --broader-okved --analyze

    # Save results
    python -m scripts.run_sonko_import --xlsx data/sonko/sonko_organizations.xlsx --limit 10 --output data/sonko/results.json
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SONKO registry pipeline for Navigator Harvester"
    )

    parser.add_argument(
        "--xlsx",
        type=str,
        default="data/sonko/sonko_organizations.xlsx",
        help="Path to SONKO XLSX file (default: data/sonko/sonko_organizations.xlsx)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download XLSX from data.economy.gov.ru before processing",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze only: show filter statistics",
    )
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without sending to Core",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max organizations to process (after filtering)",
    )
    parser.add_argument(
        "--broader-okved",
        action="store_true",
        help="Include broader OKVED codes (86, 93, 96) in addition to 87, 88",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Save results JSON to this path",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay between organizations (seconds, default 1.5)",
    )

    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    from config.logging import configure_logging
    configure_logging()

    if args.download:
        from aggregators.sonko.xlsx_parser import download_xlsx
        dest = args.xlsx
        print(f"Downloading SONKO XLSX to {dest}...")
        download_xlsx(dest)
        print(f"Done. File saved to {dest}")
        if not args.analyze:
            return

    if not os.path.exists(args.xlsx):
        print(f"ERROR: XLSX file not found: {args.xlsx}")
        print("Run with --download to fetch it from data.economy.gov.ru.")
        sys.exit(1)

    if args.analyze:
        await _run_analyze(args)
    else:
        await _run_pipeline(args)


async def _run_analyze(args: argparse.Namespace) -> None:
    from aggregators.sonko.sonko_pipeline import SONKOPipeline

    pipeline = SONKOPipeline()
    stats = await pipeline.analyze_only(
        args.xlsx,
        include_broader_okved=args.broader_okved,
    )
    print()
    print(stats.summary())


async def _run_pipeline(args: argparse.Namespace) -> None:
    from aggregators.sonko.sonko_pipeline import SONKOPipeline

    pipeline = SONKOPipeline(delay_between_orgs=args.delay)
    report = await pipeline.run(
        xlsx_path=args.xlsx,
        limit=args.limit,
        dry_run=args.dry_run,
        include_broader_okved=args.broader_okved,
        output_path=args.output,
    )

    print()
    print(report.summary())

    if args.dry_run and report.results:
        print()
        print("=== Dry-run results (first 20) ===")
        for r in report.results[:20]:
            website = r.discovered_website or "no website"
            print(f"  OKVED={r.okved:>7} | {r.name[:60]}")
            print(f"             INN={r.inn} | {r.address[:50]} | {website}")

    if args.output:
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
