#!/usr/bin/env bash
# Run auto_enrich in background with TMPDIR set in this shell so Chromium
# inherits it (fixes "unable to open database file" when using nohup).
# Usage: cd ai-pipeline/harvester && bash scripts/run_auto_enrich_background.sh 2026-02-25_no_sources
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"
export TMPDIR="${SCRIPT_DIR}/data/browser_profile"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export PLAYWRIGHT_BROWSERS_PATH="${SCRIPT_DIR}/data/playwright_browsers"
mkdir -p "$TMPDIR" "$PLAYWRIGHT_BROWSERS_PATH"
RUN_ID="${1:?Usage: run_auto_enrich_background.sh <run-id> [args...]}"
shift
LOG_FILE="${SCRIPT_DIR}/data/runs/${RUN_ID}/wrapper.log"
mkdir -p "$(dirname "$LOG_FILE")"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting in background, TMPDIR=$TMPDIR" | tee -a "$LOG_FILE"
nohup env TMPDIR="$TMPDIR" TMP="$TMPDIR" TEMP="$TMPDIR" bash "$SCRIPT_DIR/scripts/run_auto_enrich.sh" "$RUN_ID" "$@" >> "$LOG_FILE" 2>&1 &
echo "PID=$! Log: tail -f $LOG_FILE"
echo "To stop: kill $!"
