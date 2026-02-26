#!/usr/bin/env python3
"""Import Silver Age (silveragemap.ru) events into Navigator Core.

Events are tied to a single "platform" organizer (Коалиция «Забота рядом»).
If the organizer does not exist, it is created with source_reference silverage_platform.

Usage:
    # Import all events (scrape + write to Core)
    python -m scripts.import_silverage_events

    # Limit number of events
    python -m scripts.import_silverage_events --limit 5

    # Dry-run (scrape only, no API calls)
    python -m scripts.import_silverage_events --dry-run

    # Use existing organizer UUID (skip get-or-create)
    python -m scripts.import_silverage_events --organizer-id <uuid>
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aggregators.silverage.models import SilverAgeEvent
from aggregators.silverage.scraper import SilverAgeScraper
from config.settings import get_settings
from core_client.api import NavigatorCoreClient
from utils.date_parse import parse_date_text_to_iso


SILVERAGE_PLATFORM_SOURCE_REF = "silverage_platform"
PLATFORM_TITLE = "Коалиция «Забота рядом» / silveragemap.ru"


async def get_or_create_platform_organizer(core: NavigatorCoreClient) -> str | None:
    """Return organizer_id for Silver Age platform. Create organizer if missing."""
    # Lookup by source_reference (Organization with this ref → its organizer)
    data = await core.lookup_organization(source_reference=SILVERAGE_PLATFORM_SOURCE_REF)
    if data and data.get("organizer_id"):
        return data["organizer_id"]

    # Create minimal platform organization
    payload = {
        "source_reference": SILVERAGE_PLATFORM_SOURCE_REF,
        "entity_type": "Organization",
        "title": PLATFORM_TITLE,
        "description": "Агрегатор практик и мероприятий для людей старшего возраста. Сайт silveragemap.ru.",
        "ai_metadata": {
            "decision": "accepted",
            "ai_confidence_score": 0.95,
            "works_with_elderly": True,
            "ai_explanation": "Платформа-агрегатор Silver Age для импорта мероприятий.",
            "ai_source_trace": [
                {
                    "source_kind": "platform_silverage",
                    "source_url": "https://silveragemap.ru/meropriyatiya/",
                    "fields_extracted": ["events_list"],
                }
            ],
        },
        "classification": {
            "organization_type_codes": ["142"],
            "ownership_type_code": "162",
            "thematic_category_codes": [],
            "service_codes": [],
            "specialist_profile_codes": [],
        },
        "venues": [],
    }
    resp = await core.import_organizer(payload)
    return resp.get("organizer_id")


def event_to_payload(event: SilverAgeEvent, organizer_id: str) -> dict:
    """Build Core API import/event payload from SilverAgeEvent."""
    attendance_mode = "online" if event.is_online else "offline"
    online_url = event.registration_url or (event.page_url if event.is_online else None)

    desc = event.description[:2000] if event.description else ""

    start_iso, end_iso = parse_date_text_to_iso(event.date_text or "")

    payload = {
        "source_reference": event.source_reference,
        "organizer_id": organizer_id,
        "title": event.title,
        "description": desc or None,
        "attendance_mode": attendance_mode,
        "online_url": online_url,
        "event_page_url": event.page_url,
        "rrule_string": None,
        "ai_metadata": {
            "decision": "accepted",
            "ai_confidence_score": 0.8,
            "works_with_elderly": True,
            "ai_explanation": (
                "Мероприятие с сайта silveragemap.ru (Коалиция «Забота рядом»). "
                "Все мероприятия на сайте посвящены работе с пожилыми людьми."
            ),
            "ai_source_trace": [
                {
                    "source_kind": "platform_silverage",
                    "source_url": event.page_url,
                    "fields_extracted": ["title", "date", "location", "description"],
                }
            ],
        },
        "classification": {
            "event_category_codes": [],
            "thematic_category_codes": [],
            "target_audience": ["elderly"],
        },
    }
    if start_iso and end_iso:
        payload["start_datetime"] = start_iso
        payload["end_datetime"] = end_iso
    return payload


async def run(
    limit: int | None = None,
    dry_run: bool = False,
    organizer_id: str | None = None,
    cache_dir: str | None = None,
) -> list[dict]:
    settings = get_settings()
    core = NavigatorCoreClient(
        base_url=settings.core_api_url,
        api_token=settings.core_api_token,
    )

    if core.mock_mode:
        print("WARNING: CORE_API_URL not set — mock mode, no real DB writes.")
        print()

    scraper = SilverAgeScraper(delay=1.0, cache_dir=cache_dir)
    events: list[SilverAgeEvent] = await scraper.scrape_all_events()

    if limit:
        events = events[:limit]

    print(f"Scraped {len(events)} events from silveragemap.ru")
    if not events:
        return []

    if dry_run:
        print("DRY-RUN: would import the following events (no API calls):")
        for e in events:
            print(f"  - {e.title[:60]} | {e.date_text} | {'online' if e.is_online else 'offline'}")
        return []

    oid = organizer_id
    if not oid:
        oid = await get_or_create_platform_organizer(core)
        if not oid:
            print("ERROR: Could not get or create platform organizer.")
            return []
        print(f"Platform organizer: {oid}")
    else:
        print(f"Using provided organizer_id: {oid}")

    created: list[dict] = []
    for i, event in enumerate(events, 1):
        payload = event_to_payload(event, oid)
        try:
            resp = await core.import_event(payload)
            eid = resp.get("event_id")
            status = resp.get("assigned_status", "?")
            created.append({
                "event_id": eid,
                "title": event.title,
                "date_text": event.date_text,
                "attendance_mode": "online" if event.is_online else "offline",
                "page_url": event.page_url,
                "assigned_status": status,
            })
            print(f"  [{i}/{len(events)}] {event.title[:50]} → event_id={eid} status={status}")
        except Exception as e:
            print(f"  [{i}/{len(events)}] ERROR {event.title[:40]}: {e}")
        await asyncio.sleep(0.3)

    return created


def main():
    parser = argparse.ArgumentParser(description="Import Silver Age events into Navigator Core")
    parser.add_argument("--limit", type=int, default=None, help="Max events to import")
    parser.add_argument("--dry-run", action="store_true", help="Scrape only, do not call API")
    parser.add_argument("--organizer-id", type=str, default=None, help="Use this organizer UUID (skip get-or-create)")
    parser.add_argument("--cache-dir", type=str, default=None, help="Cache dir for scraper")
    parser.add_argument("--output", "-o", type=str, default=None, help="Write created cards JSON to file")
    args = parser.parse_args()

    created = asyncio.run(run(
        limit=args.limit,
        dry_run=args.dry_run,
        organizer_id=args.organizer_id,
        cache_dir=args.cache_dir,
    ))

    if created:
        print()
        print("=== Созданные карточки мероприятий ===")
        for c in created:
            print(f"  {c['title'][:60]}")
            print(f"    event_id: {c['event_id']} | {c['attendance_mode']} | {c['date_text']}")
            print(f"    URL: {c['page_url']}")
            print()
        if args.output:
            out_path = args.output
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(created, f, ensure_ascii=False, indent=2)
            print(f"Saved {len(created)} cards to {out_path}")

    return 0 if not args.dry_run or not created else 0


if __name__ == "__main__":
    sys.exit(main())
