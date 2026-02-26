#!/usr/bin/env bash
#
# Wrapper for auto_enrich.py with auto-restart (up to MAX_RETRIES).
# Crash recovery is handled by auto_enrich.py itself via progress.jsonl —
# each restart picks up from where it left off.
#
# Usage:
#   cd ai-pipeline/harvester
#   bash scripts/run_auto_enrich.sh <run-id> [extra args...]
#
# Examples:
#   bash scripts/run_auto_enrich.sh 2026-02-25_no_sources
#   bash scripts/run_auto_enrich.sh 2026-02-25_no_sources --max-items 100
#
# Background:
#   nohup bash scripts/run_auto_enrich.sh 2026-02-25_no_sources \
#     > data/runs/2026-02-25_no_sources/wrapper.log 2>&1 &

set -euo pipefail

MAX_RETRIES=3
RETRY_DELAY=30  # seconds between retries

if [ $# -lt 1 ]; then
  echo "Usage: $0 <run-id> [extra args for auto_enrich.py]"
  exit 1
fi

RUN_ID="$1"
shift
EXTRA_ARGS=("$@")

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$SCRIPT_DIR/data/runs/$RUN_ID"
mkdir -p "$RUN_DIR"

LOG_FILE="$RUN_DIR/wrapper.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

attempt=0

while [ $attempt -lt $MAX_RETRIES ]; do
  attempt=$((attempt + 1))
  log "=== Attempt $attempt/$MAX_RETRIES ==="
  log "Run ID: $RUN_ID"
  log "Args: ${EXTRA_ARGS[*]:-none}"

  set +e
  python -m scripts.auto_enrich --run-id "$RUN_ID" "${EXTRA_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
  EXIT_CODE=${PIPESTATUS[0]}
  set -e

  if [ $EXIT_CODE -eq 0 ]; then
    log "=== Completed successfully ==="
    exit 0
  fi

  log "=== Process exited with code $EXIT_CODE ==="

  if [ $attempt -lt $MAX_RETRIES ]; then
    log "Restarting in ${RETRY_DELAY}s (attempt $((attempt + 1))/$MAX_RETRIES)..."
    sleep $RETRY_DELAY
  fi
done

log "=== All $MAX_RETRIES attempts exhausted. Giving up. ==="
log "Check $RUN_DIR/run_summary.json for progress."
log "To resume manually: python -m scripts.auto_enrich --run-id $RUN_ID"
exit 1
