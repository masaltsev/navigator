#!/usr/bin/env python3
"""
Background runner: discover and create sources for organizations without any.

Reads organizations via Core API, processes each through EnrichmentPipeline,
creates sources via API for AUTO tier, saves REVIEW/REJECT to JSON.

Designed for long unattended runs with crash recovery (JSONL progress file).

Usage:
  cd ai-pipeline/harvester

  # Test run — first 20 items
  python -m scripts.auto_enrich --run-id test_20 --max-items 20

  # Full run (foreground)
  python -m scripts.auto_enrich --run-id 2026-02-25_no_sources

  # Resume after crash (same run-id)
  python -m scripts.auto_enrich --run-id 2026-02-25_no_sources

  # Background (nohup)
  nohup python -m scripts.auto_enrich --run-id 2026-02-25_no_sources \
    > data/runs/2026-02-25_no_sources/stdout.log 2>&1 &
"""

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_harvester_root = Path(__file__).resolve().parent.parent
if str(_harvester_root) not in sys.path:
    sys.path.insert(0, str(_harvester_root))

# Set writable dirs for Chromium/Playwright before any crawl4ai import (fixes DB path and sandbox cache)
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

import structlog
from config.logging import configure_logging
from config.settings import get_settings

configure_logging()
settings = get_settings()
logger = structlog.get_logger("auto_enrich")


_shutdown_requested = False


def _signal_handler(signum, _frame):
    global _shutdown_requested
    _shutdown_requested = True
    logger.warning("shutdown_requested", signal=signal.Signals(signum).name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_core_client():
    from core_client.api import NavigatorCoreClient
    return NavigatorCoreClient(
        base_url=settings.core_api_url,
        api_token=settings.core_api_token,
    )


def _get_deepseek_client():
    from processors.deepseek_client import DeepSeekClient
    return DeepSeekClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model_name,
    )


def _get_provider():
    from search.provider import get_search_provider
    return get_search_provider()


class RunState:
    """Tracks which org_ids have been processed (crash-safe via JSONL)."""

    def __init__(self, run_dir: Path):
        self._run_dir = run_dir
        self._progress_path = run_dir / "progress.jsonl"
        self._review_path = run_dir / "review.json"
        self._reject_path = run_dir / "reject.json"
        self._summary_path = run_dir / "run_summary.json"

        self._processed_ids: set[str] = set()
        self._review_items: list[dict] = []
        self._reject_items: list[dict] = []
        self._counters = {"auto": 0, "review": 0, "reject": 0, "error": 0, "total": 0}

        run_dir.mkdir(parents=True, exist_ok=True)
        self._load_existing()

    def _load_existing(self):
        if self._progress_path.exists():
            with open(self._progress_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        self._processed_ids.add(entry["org_id"])
                        tier = entry.get("tier", "reject")
                        if tier in self._counters:
                            self._counters[tier] += 1
                        self._counters["total"] += 1
                    except (json.JSONDecodeError, KeyError):
                        continue

            logger.info(
                "resume_state_loaded",
                processed=len(self._processed_ids),
                counters=self._counters,
            )

        if self._review_path.exists():
            with open(self._review_path) as f:
                self._review_items = json.load(f)

        if self._reject_path.exists():
            with open(self._reject_path) as f:
                self._reject_items = json.load(f)

    def is_processed(self, org_id: str) -> bool:
        return org_id in self._processed_ids

    def record(self, entry: dict):
        org_id = entry["org_id"]
        tier = entry.get("tier", "reject")

        self._processed_ids.add(org_id)
        self._counters["total"] += 1
        if tier in self._counters:
            self._counters[tier] += 1

        with open(self._progress_path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        if tier == "review":
            self._review_items.append(entry)
        elif tier == "reject":
            self._reject_items.append(entry)

    def flush_json(self):
        with open(self._review_path, "w") as f:
            json.dump(self._review_items, f, ensure_ascii=False, indent=2)
        with open(self._reject_path, "w") as f:
            json.dump(self._reject_items, f, ensure_ascii=False, indent=2)

    def save_summary(self, extra: dict | None = None):
        summary = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "counters": self._counters,
            "processed": len(self._processed_ids),
        }
        if extra:
            summary.update(extra)
        with open(self._summary_path, "w") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    @property
    def counters(self) -> dict:
        return self._counters

    @property
    def processed_count(self) -> int:
        return len(self._processed_ids)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def run(args):
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    run_dir = Path("data/runs") / args.run_id
    state = RunState(run_dir)

    config_path = run_dir / "run_config.json"
    if not config_path.exists():
        with open(config_path, "w") as f:
            json.dump(vars(args), f, ensure_ascii=False, indent=2)

    core = _get_core_client()
    provider = _get_provider()
    deepseek = _get_deepseek_client()

    from search.enrichment_pipeline import EnrichmentPipeline, Tier
    from search.yandex_xml_provider import region_from_api

    pipeline = EnrichmentPipeline(
        search_provider=provider,
        deepseek_client=deepseek,
        max_verify_candidates=args.verify_top,
        auto_threshold=args.auto_threshold,
        review_threshold=args.review_threshold,
    )

    # ---- Load all orgs via paginated API ----
    all_orgs: list[dict] = []
    page = 1
    per_page = 500
    logger.info("loading_organizations_from_api")

    while True:
        resp = await core.get_orgs_without_sources(page=page, per_page=per_page)
        data = resp.get("data", [])
        meta = resp.get("meta", {})
        all_orgs.extend(data)

        total = meta.get("total", len(all_orgs))
        last_page = meta.get("last_page", 1)
        logger.info("api_page_loaded", page=page, items=len(data), total=total)

        if page >= last_page or not data:
            break
        page += 1

    # Filter already processed
    pending = [o for o in all_orgs if not state.is_processed(o["org_id"])]
    if args.max_items:
        pending = pending[:args.max_items]

    print(f"\n{'='*65}")
    print(f"  Auto-Enrich Runner: {args.run_id}")
    print(f"  Total organizations without sources: {len(all_orgs)}")
    print(f"  Already processed (resume):          {state.processed_count}")
    print(f"  Pending this run:                    {len(pending)}")
    print(f"  Provider: {provider.engine_name}")
    print(f"  Core API: {'LIVE' if not core.mock_mode else 'MOCK'}")
    print(f"  Batch: {args.batch_size} items, {args.batch_delay}s delay")
    print(f"  Thresholds: auto >= {args.auto_threshold}, review >= {args.review_threshold}")
    print(f"{'='*65}\n")

    if not pending:
        print("Nothing to process. All organizations already handled.")
        return

    t_start = time.monotonic()
    batch_count = 0

    for i, org in enumerate(pending, 1):
        if _shutdown_requested:
            print(f"\n  Shutdown requested. Processed {i - 1} items this session.")
            break

        org_id = org["org_id"]
        organizer_id = org["organizer_id"]
        title = org.get("title", "(no title)")
        inn = org.get("inn", "") or ""
        city = region_from_api(
            org.get("region_iso"),
            org.get("region_code"),
            org.get("address_raw"),
        )

        label = f"[{state.processed_count + 1}/{len(all_orgs)}]"
        print(f"\n{label} {title[:60]}" + (f"  [{city}]" if city else ""))

        progress_entry: dict = {
            "org_id": org_id,
            "organizer_id": organizer_id,
            "title": title,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        try:
            result = await pipeline.enrich_missing_source(
                title, city=city, inn=inn, source_id=org_id,
            )
        except Exception as exc:
            logger.error("pipeline_error", org_id=org_id, error=str(exc))
            progress_entry.update(tier="error", error=str(exc))
            state.record(progress_entry)
            state._counters["error"] += 1
            print(f"  [ERR] {exc}")
            continue

        entry = result.to_dict()
        tier = result.tier.value
        conf = result.verification.confidence if result.verification else 0.0

        progress_entry.update(
            tier=tier,
            verified_url=result.verified_url or "",
            confidence=conf,
        )

        # AUTO: create source + import organizer data via API
        if result.tier == Tier.AUTO and result.verified_url:
            try:
                api_resp = await core.create_source(
                    organizer_id=organizer_id,
                    base_url=result.verified_url,
                    kind="org_website",
                )
                progress_entry["source_id_created"] = api_resp.get("source_id", "")
                progress_entry["api_status"] = api_resp.get("status", "")
                print(f"  [AUTO] {result.verified_url} (conf={conf:.2f}) → source created")
            except Exception as api_exc:
                logger.error("api_create_error", org_id=org_id, error=str(api_exc))
                progress_entry["api_error"] = str(api_exc)
                print(f"  [AUTO] {result.verified_url} (conf={conf:.2f}) → API error: {api_exc}")

            # Import harvested org data (categories, description, contacts, etc.)
            harvest_out = result.harvest_output or {}
            if harvest_out.get("payload"):
                try:
                    payload = harvest_out["payload"]
                    if inn:
                        payload["inn"] = inn
                    payload["site_urls"] = [result.verified_url]

                    # Only send venues that have fias_id (Dadata-verified).
                    # Unverified address_raw strings risk creating duplicate venues.
                    raw_venues = payload.get("venues", [])
                    verified_venues = [v for v in raw_venues if v.get("fias_id")]
                    payload["venues"] = verified_venues

                    venues_info = f", venues={len(verified_venues)}/{len(raw_venues)}"

                    import_resp = await core.import_organizer(payload)
                    progress_entry["org_imported"] = True
                    progress_entry["import_decision"] = payload.get("ai_metadata", {}).get("decision", "")
                    progress_entry["venues_sent"] = len(verified_venues)
                    print(f"  [IMPORT] org data sent → {import_resp.get('status', '?')}{venues_info}")
                except Exception as imp_exc:
                    logger.error("import_org_error", org_id=org_id, error=str(imp_exc))
                    progress_entry["import_error"] = str(imp_exc)
                    print(f"  [IMPORT] error: {imp_exc}")

            # Also create social sources if found
            for sp in result.social_pages:
                try:
                    await core.create_source(
                        organizer_id=organizer_id,
                        base_url=sp.url,
                        kind=sp.kind,
                    )
                    print(f"  [+social] {sp.kind}: {sp.url}")
                except Exception:
                    pass

        elif result.tier == Tier.REVIEW:
            entry["org_id"] = org_id
            entry["organizer_id"] = organizer_id
            print(f"  [REVIEW] {result.verified_url or 'no url'} (conf={conf:.2f})")

        else:
            entry["org_id"] = org_id
            entry["organizer_id"] = organizer_id

            if result.social_pages:
                created_social = []
                for sp in result.social_pages:
                    try:
                        await core.create_source(
                            organizer_id=organizer_id,
                            base_url=sp.url,
                            kind=sp.kind,
                        )
                        created_social.append(f"{sp.kind}: {sp.url}")
                        print(f"  [+social] {sp.kind}: {sp.url} (conf={sp.confidence:.2f})")
                    except Exception as exc:
                        logger.warning("social_create_error", url=sp.url, error=str(exc))
                if created_social:
                    progress_entry["social_sources_created"] = created_social
                    print(f"  [REJECT→SOCIAL] no website, but {len(created_social)} social source(s) created")
                else:
                    print(f"  [REJECT] no match, social={len(result.social_pages)} (API errors)")
            else:
                print(f"  [REJECT] no match")

        state.record(progress_entry)

        if tier == "review":
            state._review_items[-1] = entry
        elif tier == "reject":
            state._reject_items[-1] = entry

        batch_count += 1

        # Batch boundary: save JSON + stats + delay
        if batch_count >= args.batch_size:
            batch_count = 0
            state.flush_json()

            elapsed = time.monotonic() - t_start
            rate = state.counters["total"] / max(elapsed, 1) * 60
            remaining = len(pending) - i
            eta_min = remaining / max(rate, 0.1)

            c = state.counters
            print(f"\n  --- Batch checkpoint ---")
            print(f"  Progress: {state.processed_count}/{len(all_orgs)} ({100*state.processed_count/len(all_orgs):.1f}%)")
            print(f"  AUTO={c['auto']}  REVIEW={c['review']}  REJECT={c['reject']}  ERROR={c['error']}")
            print(f"  Rate: {rate:.1f} items/min | ETA: {eta_min:.0f} min")
            print(f"  Search: {provider.stats.summary()}")
            print(f"  DeepSeek: {deepseek.get_metrics()}")
            print(f"  Core API: {core.get_metrics()}")

            state.save_summary({
                "rate_per_min": round(rate, 1),
                "eta_min": round(eta_min, 0),
                "search_stats": provider.stats.summary(),
                "deepseek": deepseek.get_metrics(),
                "core_api": core.get_metrics(),
            })

            if args.batch_delay > 0 and i < len(pending):
                print(f"  Pausing {args.batch_delay}s before next batch...")
                await asyncio.sleep(args.batch_delay)

        elif i % 5 == 0:
            state.flush_json()

        if args.item_delay > 0:
            await asyncio.sleep(args.item_delay)

    # Final save
    state.flush_json()

    elapsed = time.monotonic() - t_start
    c = state.counters
    rate = c["total"] / max(elapsed, 1) * 60

    print(f"\n{'='*65}")
    print(f"  Auto-Enrich Complete: {args.run_id}")
    print(f"  Processed: {state.processed_count}/{len(all_orgs)}")
    print(f"  AUTO={c['auto']}  REVIEW={c['review']}  REJECT={c['reject']}  ERROR={c['error']}")
    print(f"  Rate: {rate:.1f} items/min | Elapsed: {elapsed/60:.1f} min")
    print(f"  Search: {provider.stats.summary()}")
    print(f"  DeepSeek: {deepseek.get_metrics()}")
    print(f"  Core API: {core.get_metrics()}")
    print(f"  Run dir: {run_dir}")
    print(f"{'='*65}\n")

    state.save_summary({
        "finished": True,
        "elapsed_min": round(elapsed / 60, 1),
        "rate_per_min": round(rate, 1),
        "search_stats": provider.stats.summary(),
        "deepseek": deepseek.get_metrics(),
        "core_api": core.get_metrics(),
    })


def main():
    parser = argparse.ArgumentParser(
        description="Auto-enrich organizations without sources (background runner)"
    )
    parser.add_argument("--run-id", required=True,
                        help="Unique run identifier (used as directory name under data/runs/)")
    parser.add_argument("--max-items", type=int, default=0,
                        help="Max items to process (0 = all)")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Items per batch before checkpoint + pause (default: 50)")
    parser.add_argument("--batch-delay", type=float, default=10.0,
                        help="Seconds to pause between batches (default: 10)")
    parser.add_argument("--item-delay", type=float, default=2.0,
                        help="Seconds between individual items (default: 2)")
    parser.add_argument("--verify-top", type=int, default=3,
                        help="Max candidates to crawl+verify per org (default: 3)")
    parser.add_argument("--auto-threshold", type=float, default=0.8,
                        help="Min confidence for AUTO tier (default: 0.8)")
    parser.add_argument("--review-threshold", type=float, default=0.5,
                        help="Min confidence for REVIEW tier (default: 0.5)")

    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
