#!/usr/bin/env python3
"""Run full enrichment for a single organization: search/verify → harvest → events → optional Core.

Uses only existing infra: EnrichmentPipeline, run_organization_harvest, EventDiscoverer,
event_ingestion, core_client. Full flow: find source (or verify --url), multi-page crawl,
OrganizationProcessor (description, INN, classification), Dadata venues, event discovery,
event ingestion (LLM classification), optional import to Core.

Usage:
  cd ai-pipeline/harvester

  # By name + region (search → verify → harvest → events)
  python -m scripts.run_single_org_enrichment "ОГБУ СО «Октябрьский геронтологический центр»" "Костромская область"

  # With known URL (verify → harvest → events, no search)
  python -m scripts.run_single_org_enrichment "ОГБУ СО Октябрьский геронтологический центр" "Костромская область" --url https://example.com

  # Send to Core (org + source record + events)
  python -m scripts.run_single_org_enrichment "Название" "Регион" --to-core
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))
_env = _harvester_root / ".env"
if _env.exists():
    from dotenv import load_dotenv
    load_dotenv(_env)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Full enrichment for one org (existing pipeline only)")
    parser.add_argument("org_title", help="Organization full name")
    parser.add_argument("region", nargs="?", default="", help="Region/city (e.g. Костромская область)")
    parser.add_argument("--url", default="", help="If set, verify this URL instead of searching")
    parser.add_argument("--skip-verify", action="store_true", help="With --url: skip SiteVerifier, run harvest directly (for known-good URLs)")
    parser.add_argument("--inn", default="", help="Optional INN for verification")
    parser.add_argument("--to-core", action="store_true", help="Import org + source + events to Core API")
    parser.add_argument("--no-events", action="store_true", help="Skip event discovery and ingestion")
    args = parser.parse_args()

    from config.logging import configure_logging
    from config.settings import get_settings
    from processors.deepseek_client import DeepSeekClient
    from search.enrichment_pipeline import EnrichmentPipeline, Tier
    from search.provider import get_search_provider

    configure_logging()
    settings = get_settings()
    provider = get_search_provider()
    if not provider:
        print("ERROR: No search provider (set SEARCH_PROVIDER and/or Yandex/DDG keys)")
        sys.exit(1)

    llm = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model_name,
    )
    pipeline = EnrichmentPipeline(provider, llm)

    print(f"Provider: {type(provider).__name__}")
    print(f"Org: {args.org_title}")
    print(f"Region: {args.region or '(empty)'}")
    if args.url:
        print(f"URL (verify): {args.url}")
    print()

    # --- Step 1: get verified URL (search or verify known URL) ---
    if args.url.strip():
        if args.skip_verify:
            result = type("_R", (), {"verified_url": args.url.strip(), "tier": Tier.AUTO, "all_verifications": [], "error": None})()
        else:
            result = await pipeline.enrich_broken_url(
                args.url.strip(),
                args.org_title,
                city=args.region,
                inn=args.inn or "",
                source_id="single_run",
                additional_context="",
                source_kind="org_website",
            )
    else:
        result = await pipeline.enrich_missing_source(
            args.org_title,
            city=args.region,
            inn=args.inn or "",
            source_id="single_run",
            additional_context="",
            source_kind="org_website",
        )

    if not result.verified_url:
        print("=== No verified URL ===")
        print(f"  tier: {result.tier.value}")
        print(f"  verifications: {len(result.all_verifications)}")
        for v in result.all_verifications:
            print(f"    {v.url[:70]} confidence={v.confidence} is_match={v.is_match}")
        if result.error:
            print(f"  error: {result.error}")
        return

    url = result.verified_url
    print(f"Verified URL: {url}")
    print()

    # --- Step 2: full harvest (multi-page crawl, site extractor, OrganizationProcessor, Dadata) ---
    from harvest.run_organization_harvest import run_organization_harvest

    print("Running harvest (multi-page, Dadata venues, site extractor)...")
    harvest_out = await run_organization_harvest(
        url,
        source_id="single_run",
        source_item_id=url,
        existing_entity_id=None,
        multi_page=True,
        enrich_geo=True,
        additional_context="",
        source_kind="org_website",
        try_site_extractor=True,
        deepseek_client=llm,
    )

    if not harvest_out["success"]:
        print(f"Harvest failed: {harvest_out.get('error')}")
        return

    org_result = harvest_out["result"]
    payload = harvest_out["payload"]
    print("=== Organization (harvest) ===")
    print(f"  title: {payload.get('title', '')[:80]}")
    print(f"  short_title: {payload.get('short_title')}")
    print(f"  inn: {payload.get('inn')}")
    print(f"  description: {(payload.get('description') or '')[:200]}...")
    print(f"  venues: {len(payload.get('venues') or [])}")
    print(f"  ai_decision: {org_result.ai_metadata.decision} confidence={org_result.ai_metadata.ai_confidence_score}")
    print()

    # --- Step 3: event discovery + ingestion ---
    event_payloads: list[dict] = []
    if not args.no_events:
        from strategies.event_discovery import EventDiscoverer
        from event_ingestion import run_event_ingestion_pipeline
        from event_ingestion.adapters import event_candidate_to_raw

        discoverer = EventDiscoverer(max_event_pages=3, max_events_per_page=10)
        discovery = await discoverer.discover_events(url)
        print(f"Event discovery: {discovery.event_pages_found} pages, {len(discovery.candidates)} candidates")

        # organizer_id needed only when sending to Core; for events we'll get it after import_organizer
        organizer_id_for_events: str | None = None
        if args.to_core:
            # We'll set after import_organizer
            pass
        else:
            # Still run ingestion to show classification; use placeholder so payload is buildable
            organizer_id_for_events = "00000000-0000-0000-0000-000000000000"

        for candidate in discovery.candidates:
            raw = event_candidate_to_raw(candidate, source_id=url)
            ev_payload = run_event_ingestion_pipeline(
                raw,
                organizer_id_for_events or "00000000-0000-0000-0000-000000000000",
                use_llm_classification=True,
                title_override=candidate.title,
            )
            if ev_payload is not None:
                event_payloads.append(ev_payload)

        for i, ep in enumerate(event_payloads[:15], 1):
            print(f"  [{i}] {ep.get('title', '')[:60]} | {ep.get('start_datetime', '')} | {ep.get('event_page_url', '')[:50]}")
        if len(event_payloads) > 15:
            print(f"  ... and {len(event_payloads) - 15} more")
        print()

    # --- Step 4: optional send to Core ---
    if args.to_core:
        from core_client.api import NavigatorCoreClient

        core = NavigatorCoreClient(
            base_url=settings.core_api_url,
            api_token=settings.core_api_token,
        )
        payload["source_reference"] = payload.get("source_reference") or "single_run_" + url[:30].replace("/", "_")
        resp = await core.import_organizer(payload)
        organizer_id = resp.get("organizer_id")
        if not organizer_id:
            print("Core import_organizer did not return organizer_id")
            return
        print(f"Imported organizer: {organizer_id}")

        await core.create_source(organizer_id, url, kind="org_website")
        print("Created source record")

        if event_payloads and organizer_id:
            for ep in event_payloads:
                ep["organizer_id"] = organizer_id
                try:
                    await core.import_event(ep)
                except Exception as e:
                    print(f"  Event import error: {e}")
            print(f"Imported {len(event_payloads)} events")
    else:
        print("(Skip Core: run with --to-core to import org + source + events)")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
