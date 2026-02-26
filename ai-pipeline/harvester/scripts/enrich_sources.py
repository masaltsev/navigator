#!/usr/bin/env python3
"""
CLI: find and fix broken org_website URLs, discover missing websites and social pages.

Usage:
  cd ai-pipeline/harvester

  # Fix broken URLs via web search (truncated domains)
  python -m scripts.enrich_sources --fix-urls -i data/audit_truncated_urls.json --limit 5 --pretty

  # Fix broken URLs WITH verification (crawl + LLM check)
  python -m scripts.enrich_sources --fix-urls-verified -i data/audit_truncated_urls.json --limit 5 --pretty

  # Fix URLs that just need https:// prepended (no search, fast)
  python -m scripts.enrich_sources --fix-scheme -i data/audit_missing_scheme.json -o data/results_scheme.json

  # Check reachability of cyrillic/IDN URLs (no search)
  python -m scripts.enrich_sources --check-reachable -i data/audit_cyrillic.json -o data/results_cyrillic.json

  # Discover sites for a single org by name
  python -m scripts.enrich_sources --org-title "КЦСОН Вологды" --city "Вологда"

  # Find missing websites for orgs from a JSON file
  python -m scripts.enrich_sources --find-missing -i data/audit_no_source.json --limit 10

  # Find missing websites WITH verification (crawl + LLM)
  python -m scripts.enrich_sources --find-missing-verified -i data/audit_no_source.json --limit 10

Input JSON: fields 'base_url'/'url' and 'org_title'/'title' are auto-normalised.
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
logger = structlog.get_logger("enrich_sources")


def _get_deepseek_client():
    """Create a DeepSeekClient with correct model name from settings."""
    from processors.deepseek_client import DeepSeekClient
    return DeepSeekClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model_name,
    )


def _get_provider():
    """Pick the best available search provider."""
    from search.provider import get_search_provider
    return get_search_provider()


async def cmd_fix_urls(args):
    """Scenario A: fix broken org_website URLs."""
    from search.url_fixer import fix_broken_url

    provider = _get_provider()
    sources = _load_input(args.input, required_fields=["url"])

    if args.offset:
        sources = sources[args.offset:]
    if args.limit:
        sources = sources[:args.limit]

    start_idx = args.offset or 0

    print(f"\n{'='*60}")
    print(f"  Fix broken URLs — {len(sources)} source(s) (offset {start_idx})")
    print(f"  Provider: {provider.engine_name}")
    print(f"  Dry-run: {args.dry_run}")
    print(f"{'='*60}\n")

    fixed_count = 0
    error_count = 0
    results_log = []

    for i, src in enumerate(sources, 1):
        url = src["url"]
        org_title = src.get("org_title", src.get("title", ""))
        city = src.get("city", src.get("city_address", ""))
        source_id = src.get("source_id", f"item-{i + start_idx}")

        print(f"[{i + start_idx}/{start_idx + len(sources)}] {url}")

        try:
            result = await fix_broken_url(
                url,
                provider,
                org_title=org_title,
                city=city,
                verify_reachable=not args.skip_verify,
            )
        except Exception as exc:
            error_count += 1
            print(f"  ✗ Error: {exc}")
            results_log.append({
                "source_id": source_id, "original_url": url,
                "org_title": org_title, "fixed": False, "error": str(exc),
            })
            if args.output:
                _save_output(args.output, results_log)
            continue

        entry = {
            "source_id": source_id,
            "original_url": url,
            "org_title": org_title,
            "fragment": result.fragment,
            "search_results": result.search_results_count,
            "candidates": len(result.candidates),
            "fixed": result.fixed,
        }

        if result.best:
            entry["best_url"] = result.best.url
            entry["best_score"] = result.best.score
            entry["best_reachable"] = result.best.reachable
            entry["best_reason"] = result.best.reason
            fixed_count += 1
            print(f"  ✓ Found: {result.best.url} (score={result.best.score})")
        else:
            print(f"  ✗ No suitable replacement found")

        if args.pretty:
            for c in result.candidates[:3]:
                marker = "✓" if c.reachable else "?"
                print(f"    [{marker}] {c.url} score={c.score} {c.reason}")

        results_log.append(entry)

        if args.output and i % 10 == 0:
            _save_output(args.output, results_log)

    _print_summary("URL Fix", len(sources), fixed_count, provider)
    if error_count:
        print(f"  Errors: {error_count}")

    if args.output:
        _save_output(args.output, results_log)

    return results_log


async def cmd_find_missing(args):
    """Scenario B+C: discover websites and social pages for orgs without sources."""
    from search.source_discoverer import discover_sources

    provider = _get_provider()
    orgs = _load_input(args.input, required_fields=["title"])

    if args.limit:
        orgs = orgs[:args.limit]

    print(f"\n{'='*60}")
    print(f"  Discover missing sources — {len(orgs)} org(s)")
    print(f"  Provider: {provider.engine_name}")
    print(f"  Dry-run: {args.dry_run}")
    print(f"{'='*60}\n")

    found_count = 0
    results_log = []

    for i, org in enumerate(orgs, 1):
        title = org["title"]
        city = org.get("city", "")
        org_id = org.get("org_id", f"item-{i}")

        print(f"[{i}/{len(orgs)}] {title} ({city})")

        result = await discover_sources(
            title,
            provider,
            city=city,
            verify_reachable=not args.skip_verify,
        )

        entry = {
            "org_id": org_id,
            "title": title,
            "city": city,
            "query": result.query_used,
            "search_results": result.search_results_count,
            "found": result.found_anything,
            "official_sites": [
                {"url": s.url, "confidence": s.confidence, "reachable": s.reachable}
                for s in result.official_sites
            ],
            "social_pages": [
                {"url": s.url, "kind": s.kind, "slug": s.social_link.slug if s.social_link else ""}
                for s in result.social_pages
            ],
        }

        if result.found_anything:
            found_count += 1
            best = result.best_official
            if best:
                print(f"  ✓ Official: {best.url} (conf={best.confidence:.2f})")
            for sp in result.social_pages:
                print(f"  ✓ Social [{sp.kind}]: {sp.url}")
        else:
            print(f"  ✗ Nothing found")

        results_log.append(entry)

    _print_summary("Source Discovery", len(orgs), found_count, provider)

    if args.output:
        _save_output(args.output, results_log)

    return results_log


async def cmd_fix_scheme(args):
    """Fix URLs that are only missing the https:// scheme prefix."""
    from search.url_fixer import check_url_reachable

    sources = _load_input(args.input, required_fields=["url"])
    if args.limit:
        sources = sources[: args.limit]

    print(f"\n{'='*60}")
    print(f"  Fix missing scheme — {len(sources)} source(s)")
    print(f"{'='*60}\n")

    fixed = 0
    unreachable = 0
    results_log = []

    emails_skipped = 0
    for i, src in enumerate(sources, 1):
        raw = src["url"].strip()
        source_id = src.get("source_id", f"item-{i}")
        org_title = src.get("title", src.get("org_title", ""))

        if "@" in raw:
            emails_skipped += 1
            print(f"[{i}/{len(sources)}] — {raw:<45}  (email, skipped)")
            results_log.append({
                "source_id": source_id, "original_url": raw,
                "org_title": org_title, "status": "email",
            })
            continue

        if raw.startswith("http://") or raw.startswith("https://"):
            candidate = raw
        else:
            candidate = f"https://{raw}"

        reachable = await check_url_reachable(candidate) if not args.skip_verify else None
        if reachable is False:
            fallback = candidate.replace("https://", "http://", 1)
            reachable = await check_url_reachable(fallback)
            if reachable:
                candidate = fallback

        status = "ok" if reachable else ("skip" if reachable is None else "unreachable")
        if reachable:
            fixed += 1
        elif reachable is False:
            unreachable += 1

        tag = {"ok": "✓", "skip": "?", "unreachable": "✗"}[status]
        print(f"[{i}/{len(sources)}] {tag} {raw:<45} -> {candidate}")

        results_log.append({
            "source_id": source_id,
            "original_url": raw,
            "fixed_url": candidate,
            "org_title": org_title,
            "reachable": reachable,
            "status": status,
        })

    actual = len(sources) - emails_skipped
    print(f"\n{'='*60}")
    print(f"  Summary: {actual} URLs checked ({emails_skipped} emails skipped)")
    print(f"  Reachable: {fixed}, Unreachable: {unreachable}")
    print(f"{'='*60}\n")

    if args.output:
        _save_output(args.output, results_log)

    return results_log


async def cmd_check_reachable(args):
    """Check reachability of existing URLs (e.g. cyrillic/IDN domains)."""
    from search.url_fixer import check_url_reachable

    sources = _load_input(args.input, required_fields=["url"])
    if args.limit:
        sources = sources[: args.limit]

    print(f"\n{'='*60}")
    print(f"  Check reachability — {len(sources)} source(s)")
    print(f"{'='*60}\n")

    reachable_count = 0
    results_log = []

    for i, src in enumerate(sources, 1):
        url = src["url"].strip()
        source_id = src.get("source_id", f"item-{i}")
        org_title = src.get("title", src.get("org_title", ""))

        if not url.startswith("http"):
            url = f"https://{url}"

        ok = await check_url_reachable(url)
        if ok:
            reachable_count += 1

        tag = "✓" if ok else "✗"
        print(f"[{i}/{len(sources)}] {tag} {url}")

        results_log.append({
            "source_id": source_id,
            "url": url,
            "org_title": org_title,
            "reachable": ok,
        })

    print(f"\n{'='*60}")
    print(f"  Summary: {len(sources)} total, {reachable_count} reachable, "
          f"{len(sources) - reachable_count} unreachable")
    print(f"{'='*60}\n")

    if args.output:
        _save_output(args.output, results_log)

    return results_log


async def _run_tiered_pipeline(args, mode: str):
    """Shared logic for --fix-urls-verified and --find-missing-verified.

    Outputs 3 tiered JSON files:
      {output}_auto.json   — conf >= 0.8, harvested, ready for auto-import
      {output}_review.json — 0.5 <= conf < 0.8 or needs_review, awaits human
      {output}_reject.json — conf < 0.5, social-only, errors
    """
    from search.enrichment_pipeline import EnrichmentPipeline, Tier

    provider = _get_provider()
    deepseek = _get_deepseek_client()
    pipeline = EnrichmentPipeline(
        search_provider=provider,
        deepseek_client=deepseek,
        max_verify_candidates=args.verify_top or 3,
        auto_threshold=args.auto_threshold,
        review_threshold=args.review_threshold,
    )

    if mode == "fix":
        items = _load_input(args.input, required_fields=["url"])
    else:
        items = _load_input(args.input, required_fields=["title"])

    if args.offset:
        items = items[args.offset:]
    if args.limit:
        items = items[:args.limit]

    start_idx = args.offset or 0

    print(f"\n{'='*60}")
    print(f"  {'Fix broken URLs' if mode == 'fix' else 'Discover missing sources'} (TIERED)")
    print(f"  Items: {len(items)} (offset {start_idx})")
    print(f"  Provider: {provider.engine_name}")
    print(f"  Thresholds: auto >= {args.auto_threshold}, review >= {args.review_threshold}")
    print(f"{'='*60}\n")

    tiers = {Tier.AUTO: [], Tier.REVIEW: [], Tier.REJECT: []}
    error_count = 0

    for i, item in enumerate(items, 1):
        url = item.get("url", "")
        org_title = item.get("org_title", item.get("title", ""))
        city = item.get("city", item.get("city_address", ""))
        inn = item.get("inn", "")
        source_id = item.get("source_id", item.get("org_id", f"item-{i + start_idx}"))

        org_title = org_title or f"(no title, item {i + start_idx})"
        city = city or ""

        label = f"[{i + start_idx}/{start_idx + len(items)}]"
        print(f"\n{label} {org_title[:50]}")
        if url:
            print(f"  URL: {url}")

        try:
            if mode == "fix":
                result = await pipeline.enrich_broken_url(
                    url, org_title, city=city, inn=inn, source_id=source_id,
                )
            else:
                result = await pipeline.enrich_missing_source(
                    org_title, city=city, inn=inn, source_id=source_id,
                )
        except Exception as exc:
            error_count += 1
            print(f"  ✗ Error: {exc}")
            err_entry = {"source_id": source_id, "org_title": org_title,
                         "original_url": url, "tier": "reject", "error": str(exc)}
            tiers[Tier.REJECT].append(err_entry)
            if args.output:
                _save_tiered(args.output, tiers)
            continue

        entry = result.to_dict()
        tier = result.tier
        tiers[tier].append(entry)

        tier_icon = {"auto": "✓✓", "review": "?!", "reject": "✗"}[tier.value]
        conf = result.verification.confidence if result.verification else 0.0
        if result.verified_url:
            print(f"  [{tier_icon}] {tier.value.upper()}: {result.verified_url} "
                  f"(conf={conf:.2f})")
            if result.harvest_output and "error" not in result.harvest_output:
                h_title = result.harvest_output.get("title", "")[:50]
                h_decision = result.harvest_output.get("ai_metadata", {}).get("decision", "")
                print(f"  harvest: \"{h_title}\" → {h_decision}")
        elif result.social_pages:
            print(f"  [{tier_icon}] {tier.value.upper()}: social only "
                  f"{[s.url[:50] for s in result.social_pages]}")
        else:
            print(f"  [{tier_icon}] {tier.value.upper()}: no match")

        if args.output and i % 5 == 0:
            _save_tiered(args.output, tiers)

    auto_n = len(tiers[Tier.AUTO])
    review_n = len(tiers[Tier.REVIEW])
    reject_n = len(tiers[Tier.REJECT])

    print(f"\n{'='*60}")
    print(f"  Tiered Pipeline Summary")
    print(f"  Total: {len(items)}")
    print(f"  AUTO   (≥{args.auto_threshold}):  {auto_n:>4} — harvested, auto-import ready")
    print(f"  REVIEW ({args.review_threshold}-{args.auto_threshold}): {review_n:>4} — needs human check")
    print(f"  REJECT (<{args.review_threshold}):  {reject_n:>4} — no match / social only / error")
    print(f"  Errors: {error_count}")
    print(f"  Search stats: {provider.stats.summary()}")
    print(f"  DeepSeek:    {deepseek.get_metrics()}")
    print(f"{'='*60}\n")

    if args.output:
        _save_tiered(args.output, tiers)

    return tiers


async def cmd_fix_urls_verified(args):
    """Scenario A with verification: fix broken URLs with confidence tiers."""
    return await _run_tiered_pipeline(args, mode="fix")


async def cmd_find_missing_verified(args):
    """Scenario B with verification: discover + verify websites with confidence tiers."""
    return await _run_tiered_pipeline(args, mode="discover")


async def cmd_single_org(args):
    """Search for a single org by title and city."""
    from search.source_discoverer import discover_sources

    provider = _get_provider()

    print(f"\nSearching for: \"{args.org_title}\" {args.city or ''}")
    print(f"Provider: {provider.engine_name}\n")

    result = await discover_sources(
        args.org_title,
        provider,
        city=args.city or "",
        verify_reachable=not args.skip_verify,
    )

    print(f"Query: {result.query_used}")
    print(f"Results: {result.search_results_count}")
    print(f"Skipped aggregators: {result.skipped_aggregators}\n")

    if result.official_sites:
        print("Official websites:")
        for s in result.official_sites:
            marker = "✓" if s.reachable else "?"
            print(f"  [{marker}] {s.url} (confidence={s.confidence:.2f})")
    else:
        print("No official websites found.")

    if result.social_pages:
        print("\nSocial pages:")
        for s in result.social_pages:
            slug = s.social_link.slug if s.social_link else ""
            print(f"  [{s.kind}] {s.url} (slug={slug})")

    print(f"\nSearch stats: {provider.stats.summary()}")


_FIELD_ALIASES = {
    "url": ["base_url"],
    "title": ["org_title"],
    "city": ["city_address"],
}


def _load_input(path: str | None, required_fields: list[str]) -> list[dict]:
    """Load input from JSON file or stdin, normalising field names."""
    if path:
        with open(path) as f:
            data = json.load(f)
    else:
        if sys.stdin.isatty():
            print("No --input file specified. Reading from stdin (Ctrl+D to finish)...")
        data = json.load(sys.stdin)

    if not isinstance(data, list):
        data = [data]

    for item in data:
        for canonical, aliases in _FIELD_ALIASES.items():
            if canonical not in item:
                for alias in aliases:
                    if alias in item:
                        item[canonical] = item[alias]
                        break

    for item in data:
        for fld in required_fields:
            if fld not in item:
                raise ValueError(f"Input item missing required field '{fld}': {item}")

    return data


def _print_summary(task: str, total: int, success: int, provider):
    print(f"\n{'='*60}")
    print(f"  {task} Summary")
    print(f"  Total: {total}, Found: {success} ({100*success/max(total,1):.0f}%)")
    print(f"  Search stats: {provider.stats.summary()}")
    print(f"{'='*60}\n")


def _save_output(path: str, data: list[dict]):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Results saved to {path}")


def _save_tiered(base_path: str, tiers: dict):
    """Save tiered results to 3 separate JSON files."""
    from search.enrichment_pipeline import Tier

    stem = base_path.rsplit(".", 1)[0] if "." in base_path else base_path

    for tier in (Tier.AUTO, Tier.REVIEW, Tier.REJECT):
        path = f"{stem}_{tier.value}.json"
        with open(path, "w") as f:
            json.dump(tiers[tier], f, ensure_ascii=False, indent=2)

    counts = {t.value: len(v) for t, v in tiers.items()}
    print(f"Saved: {counts} → {stem}_*.json")


def main():
    parser = argparse.ArgumentParser(
        description="Enrich org_website sources: fix broken URLs, discover missing sites"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fix-urls", action="store_true",
                       help="Fix broken org_website URLs via web search (truncated domains)")
    group.add_argument("--fix-urls-verified", action="store_true",
                       help="Fix broken URLs WITH crawl+LLM verification")
    group.add_argument("--fix-scheme", action="store_true",
                       help="Prepend https:// to bare URLs + reachability check (no search)")
    group.add_argument("--check-reachable", action="store_true",
                       help="Check reachability of existing URLs (e.g. cyrillic/IDN)")
    group.add_argument("--find-missing", action="store_true",
                       help="Find websites for orgs without source (scenario B)")
    group.add_argument("--find-missing-verified", action="store_true",
                       help="Find + verify websites for orgs without source (crawl+LLM)")
    group.add_argument("--org-title", type=str,
                       help="Search for a single org by title")

    parser.add_argument("--city", type=str, default="", help="City for --org-title search")
    parser.add_argument("--input", "-i", type=str, help="Input JSON file")
    parser.add_argument("--output", "-o", type=str, help="Output JSON file for results")
    parser.add_argument("--limit", type=int, help="Max number of items to process")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N items (resume)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to Core API")
    parser.add_argument("--skip-verify", action="store_true", help="Skip HEAD reachability checks")
    parser.add_argument("--pretty", action="store_true", help="Show candidate details")
    parser.add_argument("--verify-top", type=int, default=3,
                        help="Max candidates to crawl+verify per org (default: 3)")
    parser.add_argument("--auto-threshold", type=float, default=0.8,
                        help="Min confidence for AUTO tier (harvest + auto-import)")
    parser.add_argument("--review-threshold", type=float, default=0.5,
                        help="Min confidence for REVIEW tier (needs human check)")

    args = parser.parse_args()

    if args.fix_urls:
        asyncio.run(cmd_fix_urls(args))
    elif args.fix_urls_verified:
        asyncio.run(cmd_fix_urls_verified(args))
    elif args.fix_scheme:
        asyncio.run(cmd_fix_scheme(args))
    elif args.check_reachable:
        asyncio.run(cmd_check_reachable(args))
    elif args.find_missing:
        asyncio.run(cmd_find_missing(args))
    elif args.find_missing_verified:
        asyncio.run(cmd_find_missing_verified(args))
    elif args.org_title:
        asyncio.run(cmd_single_org(args))


if __name__ == "__main__":
    main()
