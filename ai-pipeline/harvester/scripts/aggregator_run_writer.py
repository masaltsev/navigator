"""Write aggregator run results into data/runs/<run_id>/ in the same format as auto_enrich.

Files produced:
  - run_config.json   — run_id + args (written at start)
  - progress.jsonl    — one JSON object per line (org/event result)
  - run_summary.json  — counters, elapsed, updated_at (written at end)
  - report.json       — full pipeline report (written by pipeline to output_path)

Use from run_silverage_import, run_fpg_import, run_sonko_import when --run-id is set.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def run_dir_path(run_id: str, base: str = "data/runs") -> Path:
    """Return Path for run directory (e.g. data/runs/2026-02-27_silverage)."""
    return Path(base) / run_id


def write_run_config(run_dir: Path, run_id: str, config: dict) -> None:
    """Write run_config.json with run_id and config (e.g. vars(args))."""
    run_dir.mkdir(parents=True, exist_ok=True)
    out = {"run_id": run_id, **config}
    (run_dir / "run_config.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_progress(run_dir: Path, entry: dict) -> None:
    """Append one JSON object as a line to progress.jsonl."""
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "progress.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_run_summary(
    run_dir: Path,
    counters: dict,
    *,
    elapsed_sec: float | None = None,
    extra: dict | None = None,
) -> None:
    """Write run_summary.json with counters and optional elapsed/extra."""
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "counters": counters,
    }
    if elapsed_sec is not None:
        summary["elapsed_sec"] = round(elapsed_sec, 2)
    if extra:
        summary.update(extra)
    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def silverage_report_to_progress_entries(report) -> list[dict]:
    """Convert Silver Age PipelineReport to list of progress entry dicts."""
    entries = []
    for r in report.org_results:
        entries.append({
            "name": r.name,
            "region": r.region,
            "practice_count": r.practice_count,
            "action": r.action,
            "core_organizer_id": r.core_organizer_id,
            "discovered_website": r.discovered_website,
            "error": r.error,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    for r in report.event_results:
        entries.append({
            "type": "event",
            "title": r.title,
            "date_text": r.date_text,
            "location": r.location,
            "page_url": r.page_url,
            "action": r.action,
            "error": r.error,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    return entries


def fpg_report_to_progress_entries(report) -> list[dict]:
    """Convert FPG PipelineReport to list of progress entry dicts."""
    entries = []
    for r in report.results:
        entries.append({
            "inn": r.inn,
            "name": r.name,
            "region": r.region,
            "project_count": r.project_count,
            "action": r.action,
            "core_organizer_id": r.core_organizer_id,
            "discovered_website": r.discovered_website,
            "harvest_decision": r.harvest_decision,
            "error": r.error,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    return entries


def sonko_report_to_progress_entries(report) -> list[dict]:
    """Convert SONKO PipelineReport to list of progress entry dicts."""
    entries = []
    for r in report.results:
        entries.append({
            "inn": r.inn,
            "name": r.name,
            "okved": r.okved,
            "address": (r.address[:200] if r.address else ""),
            "action": r.action,
            "core_organizer_id": r.core_organizer_id,
            "discovered_website": r.discovered_website,
            "harvest_decision": r.harvest_decision,
            "error": r.error,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    return entries
