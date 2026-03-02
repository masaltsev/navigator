#!/usr/bin/env python3
"""CLI for FPG (Presidential Grants Foundation) aggregator pipeline.

Usage:
    # Download XLSX from FPG open data
    python -m scripts.run_fpg_import --download

    # Analyze: stats by direction, status, elderly matches
    python -m scripts.run_fpg_import --analyze --xlsx data/fpg/projects.xlsx

    # Dry-run: show what would be imported (first 20 orgs)
    python -m scripts.run_fpg_import --xlsx data/fpg/projects.xlsx --limit 20 --dry-run

    # Import with full harvest
    python -m scripts.run_fpg_import --xlsx data/fpg/projects.xlsx --limit 50

    # Filter by specific direction
    python -m scripts.run_fpg_import --xlsx data/fpg/projects.xlsx --direction "социальное обслуживание"

    # Save results to data/runs/ (run_config.json, progress.jsonl, run_summary.json, report.json)
    python -m scripts.run_fpg_import --xlsx data/fpg/projects.xlsx --limit 10 --run-id 2026-02-27_fpg

    # Legacy: single output file
    python -m scripts.run_fpg_import --xlsx data/fpg/projects.xlsx --limit 10 --output data/fpg/results.json
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aggregators.fpg.project_filter import RELEVANT_DIRECTIONS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="FPG aggregator pipeline for Navigator Harvester"
    )

    parser.add_argument(
        "--xlsx",
        type=str,
        default="data/fpg/projects.xlsx",
        help="Path to FPG open data XLSX file (default: data/fpg/projects.xlsx)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download XLSX from FPG open data before processing",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze only: show filter statistics without processing",
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
        "--direction",
        type=str,
        default=None,
        help="Filter by specific grant direction (substring match)",
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
        from aggregators.fpg.xlsx_parser import download_xlsx
        dest = args.xlsx
        print(f"Downloading FPG XLSX to {dest}...")
        download_xlsx(dest)
        print(f"Done. File saved to {dest}")
        if not args.analyze:
            return

    if not os.path.exists(args.xlsx):
        print(f"ERROR: XLSX file not found: {args.xlsx}")
        print("Run with --download to fetch it from FPG open data.")
        sys.exit(1)

    directions = None
    if args.direction:
        directions = {
            d for d in RELEVANT_DIRECTIONS
            if args.direction.lower() in d.lower()
        }
        if not directions:
            print(f"WARNING: No matching directions for '{args.direction}'")
            print("Available directions:")
            for d in sorted(RELEVANT_DIRECTIONS):
                print(f"  - {d}")
            sys.exit(1)
        print(f"Filtering to directions: {directions}")

    if args.analyze:
        await _run_analyze(args.xlsx, directions)
    else:
        await _run_pipeline(args)


async def _run_analyze(xlsx_path: str, directions: set[str] | None) -> None:
    """Run analysis only: parse + filter + print statistics."""
    from aggregators.fpg.fpg_pipeline import FPGPipeline

    pipeline = FPGPipeline()
    stats = await pipeline.analyze_only(xlsx_path)
    print()
    print(stats.summary())


async def _run_pipeline(args: argparse.Namespace) -> None:
    """Run the full FPG pipeline."""
    import time
    from scripts.aggregator_run_writer import (
        run_dir_path,
        write_run_config,
        append_progress,
        write_run_summary,
        fpg_report_to_progress_entries,
    )
    from aggregators.fpg.fpg_pipeline import FPGPipeline

    directions = None
    if args.direction:
        directions = {
            d for d in RELEVANT_DIRECTIONS
            if args.direction.lower() in d.lower()
        }

    run_dir = run_dir_path(args.run_id) if args.run_id else None
    output_path = None
    if run_dir:
        run_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(run_dir / "report.json")
        config = {k: getattr(args, k, None) for k in ["xlsx", "limit", "direction", "delay", "dry_run"]}
        write_run_config(run_dir, args.run_id, config)
    elif args.output:
        output_path = args.output

    pipeline = FPGPipeline(delay_between_orgs=args.delay)
    t0 = time.monotonic()
    report = await pipeline.run(
        xlsx_path=args.xlsx,
        limit=args.limit,
        dry_run=args.dry_run,
        directions=directions,
        output_path=output_path,
    )
    elapsed = time.monotonic() - t0

    if run_dir:
        for entry in fpg_report_to_progress_entries(report):
            append_progress(run_dir, entry)
        counters = {
            "total": len(report.results),
            "matched": report.matched,
            "created": report.created,
            "errors": report.errors,
        }
        write_run_summary(run_dir, counters, elapsed_sec=elapsed)
        print(f"\nRun trace saved to {run_dir}")

    print()
    print(report.summary())

    if args.dry_run and report.results:
        print()
        print("=== Dry-run results (first 20) ===")
        for r in report.results[:20]:
            status = "WINNER" if r.has_winner else "applicant"
            website = r.discovered_website or "no website"
            print(f"  [{status:>9}] {r.name[:60]}")
            print(f"             INN={r.inn} | {r.region} | {r.project_count} projects | {website}")

    if args.output and not run_dir:
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
