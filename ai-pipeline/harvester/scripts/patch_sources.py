#!/usr/bin/env python3
"""
CLI: Patch sources via Navigator Core API from enrichment pipeline results.

Uses PATCH /api/internal/sources/{id} for base_url, last_status, last_crawled_at.
Core syncs organization.site_urls when base_url changes for org_website.

Usage:
  cd ai-pipeline/harvester

  # Dry-run AUTO results (preview changes, no API writes)
  python -m scripts.patch_sources --input data/results_171_merged_auto.json --dry-run

  # Apply AUTO results via Core API
  python -m scripts.patch_sources --input data/results_171_merged_auto.json

  # Apply only approved REVIEW items
  python -m scripts.patch_sources --input data/results_171_merged_review.json --only-approved

  # Generate REVIEW template (adds "approved" field for human editing)
  python -m scripts.patch_sources --input data/results_171_merged_review.json --prepare-review

  # Approve specific items interactively
  python -m scripts.patch_sources --input data/results_171_merged_review.json --interactive

Requires CORE_API_URL and CORE_API_TOKEN (or .env).
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))

_env_file = _harvester_root / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)

import httpx
import structlog
from config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def _core_headers() -> dict:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.core_api_token}",
    }


def patch_source(
    base_url_api: str,
    item: dict,
    *,
    dry_run: bool = False,
) -> dict:
    """Patch a single source via Core API (PATCH /api/internal/sources/{id}).

    Returns a change record for the audit log.
    """
    source_id = item["source_id"]
    new_url = item["verified_url"]
    old_url = item.get("original_url", "")

    if not new_url:
        return {"source_id": source_id, "status": "skipped", "reason": "no verified_url"}

    change = {
        "source_id": source_id,
        "old_url": old_url,
        "new_url": new_url,
        "confidence": item.get("confidence"),
        "org_title": item.get("org_title", ""),
        "org_name_found": item.get("org_name_found", ""),
        "actions": [],
    }

    if dry_run:
        change["actions"].append(f"PATCH sources/{source_id} base_url={new_url!r} last_status=success")
        change["status"] = "dry_run"
        return change

    url = f"{base_url_api.rstrip('/')}/api/internal/sources/{source_id}"
    payload = {
        "base_url": new_url,
        "name": new_url.replace("https://", "").replace("http://", "").rstrip("/"),
        "last_status": "success",
        "last_crawled_at": datetime.now(timezone.utc).isoformat(),
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.patch(url, json=payload, headers=_core_headers())

    if resp.status_code == 200:
        change["actions"].append("source.base_url and last_status updated via Core API")
        change["status"] = "applied"
        return change

    if resp.status_code == 404:
        change["status"] = "error"
        change["reason"] = "source not found"
        return change

    if resp.status_code == 409:
        change["status"] = "deduped"
        try:
            body = resp.json()
            change["reason"] = body.get("message", "URL conflict for organizer")
        except Exception:
            change["reason"] = "URL conflict (409)"
        change["actions"].append("Core returned 409 Conflict — another source with this URL for organizer")
        return change

    change["status"] = "error"
    try:
        body = resp.json()
        change["reason"] = body.get("message", resp.text[:200])
    except Exception:
        change["reason"] = resp.text[:200]
    return change


def prepare_review(items: list[dict], output_path: str):
    """Add 'approved' and 'notes' fields to review items for human editing."""
    for item in items:
        item.setdefault("approved", False)
        item.setdefault("notes", "")
        item.setdefault("edited_url", item.get("verified_url", ""))

    with open(output_path, "w") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"\nReview template saved to: {output_path}")
    print(f"Items: {len(items)}")
    print("\nInstructions:")
    print('  1. Open the file and review each item')
    print('  2. Set "approved": true for items to import')
    print('  3. Optionally edit "edited_url" to override the verified URL')
    print('  4. Add "notes" for context')
    print(f'  5. Run: python -m scripts.patch_sources --input {output_path} --only-approved')


def interactive_review(items: list[dict], output_path: str):
    """Interactive CLI review of items."""
    approved_count = 0
    rejected_count = 0

    for i, item in enumerate(items, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(items)}] {item.get('org_title', 'N/A')}")
        print(f"  Original URL:  {item.get('original_url', 'N/A')}")
        print(f"  Verified URL:  {item.get('verified_url', 'N/A')}")
        print(f"  Confidence:    {item.get('confidence', 'N/A')}")
        print(f"  Found name:    {item.get('org_name_found', 'N/A')}")
        print(f"  Reasoning:     {item.get('reasoning', 'N/A')[:120]}")
        print(f"  Is main page:  {item.get('is_main_page', 'N/A')}")

        while True:
            choice = input("\n  [a]pprove / [r]eject / [e]dit URL / [s]kip / [q]uit > ").strip().lower()
            if choice == "a":
                item["approved"] = True
                item["edited_url"] = item.get("verified_url", "")
                approved_count += 1
                print("  -> APPROVED")
                break
            elif choice == "r":
                item["approved"] = False
                rejected_count += 1
                print("  -> REJECTED")
                break
            elif choice == "e":
                new_url = input("  New URL: ").strip()
                if new_url:
                    item["edited_url"] = new_url
                    item["approved"] = True
                    approved_count += 1
                    print(f"  -> APPROVED with edited URL: {new_url}")
                break
            elif choice == "s":
                print("  -> SKIPPED (unchanged)")
                break
            elif choice == "q":
                print("  Quitting review...")
                break
            else:
                print("  Invalid choice. Use a/r/e/s/q")

        if choice == "q":
            break

    with open(output_path, "w") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"\nReview results saved: {output_path}")
    print(f"  Approved: {approved_count}, Rejected: {rejected_count}")
    print(f"  Skipped/remaining: {len(items) - approved_count - rejected_count}")


def main():
    parser = argparse.ArgumentParser(description="Patch sources DB from enrichment results")
    parser.add_argument("--input", "-i", required=True, help="JSON file with enrichment results")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to DB")
    parser.add_argument("--only-approved", action="store_true",
                        help="Only patch items with 'approved': true")
    parser.add_argument("--prepare-review", action="store_true",
                        help="Add review fields to JSON for human editing")
    parser.add_argument("--interactive", action="store_true",
                        help="Interactive CLI review mode")
    parser.add_argument("--output", "-o", help="Output path for audit log (default: input_audit.json)")

    args = parser.parse_args()

    with open(args.input) as f:
        items = json.load(f)

    print(f"Loaded {len(items)} items from {args.input}")

    if args.prepare_review:
        out_path = args.input.replace(".json", "_review_ready.json")
        prepare_review(items, out_path)
        return

    if args.interactive:
        out_path = args.input.replace(".json", "_reviewed.json")
        interactive_review(items, out_path)
        return

    if args.only_approved:
        before = len(items)
        items = [item for item in items if item.get("approved")]
        for item in items:
            if item.get("edited_url"):
                item["verified_url"] = item["edited_url"]
        print(f"Filtered to {len(items)} approved items (from {before})")

    if not items:
        print("No items to patch.")
        return

    if not settings.core_api_url or not settings.core_api_token:
        print("ERROR: CORE_API_URL and CORE_API_TOKEN must be set (e.g. in .env).")
        sys.exit(1)

    audit_log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_file": args.input,
        "dry_run": args.dry_run,
        "total_items": len(items),
        "changes": [],
    }

    applied = 0
    skipped = 0
    errors = 0

    try:
        for i, item in enumerate(items, 1):
            change = patch_source(
                settings.core_api_url,
                item,
                dry_run=args.dry_run,
            )
            audit_log["changes"].append(change)

            status_icon = {
                "applied": "[ok]", "dry_run": "[--]", "skipped": "[skip]",
                "error": "[ERR]", "deduped": "[dup]",
            }
            icon = status_icon.get(change["status"], "[?]")
            print(f"  {icon} [{i}/{len(items)}] {change.get('org_title', '')[:50]} "
                  f"→ {change.get('new_url', 'N/A')[:50]}")

            if change["status"] in ("applied", "deduped"):
                applied += 1
            elif change["status"] == "skipped":
                skipped += 1
            elif change["status"] == "error":
                errors += 1
                print(f"       Error: {change.get('reason')}")

        if args.dry_run:
            print(f"\nDry-run complete. {len(items)} changes previewed, nothing written.")
        else:
            print(f"\nApplied {applied} changes via Core API.")

    except Exception as exc:
        print(f"\nERROR: {exc}.")
        raise

    audit_log["applied"] = applied
    audit_log["skipped"] = skipped
    audit_log["errors"] = errors

    audit_path = args.output or args.input.replace(".json", "_audit.json")
    with open(audit_path, "w") as f:
        json.dump(audit_log, f, ensure_ascii=False, indent=2)
    print(f"Audit log: {audit_path}")

    print(f"\nSummary: applied={applied}, skipped={skipped}, errors={errors}")


if __name__ == "__main__":
    main()
