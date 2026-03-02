#!/usr/bin/env bash
# One-time setup for Harvester: install deps + Playwright Chromium.
# Run from repo root or ai-pipeline/harvester. Ensures crawl/verification works
# without manual TMPDIR or 'playwright install' on the host.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HARVESTER_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$HARVESTER_ROOT"

echo "=== Harvester environment setup ==="
echo "Root: $HARVESTER_ROOT"

if [ -n "${VIRTUAL_ENV:-}" ]; then
  PIP="$VIRTUAL_ENV/bin/pip"
  PYTHON="$VIRTUAL_ENV/bin/python"
else
  PIP="pip"
  PYTHON="python"
fi

echo "Installing Python dependencies..."
"$PIP" install -e ".[dev]" 2>/dev/null || "$PIP" install -e .

echo "Installing Playwright Chromium (required for crawl/verification)..."
export TMPDIR="${HARVESTER_ROOT}/data/browser_profile"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
mkdir -p "$TMPDIR"
"$PYTHON" -m playwright install chromium

echo "=== Setup complete ==="
echo "Run auto-enrich: bash scripts/run_auto_enrich.sh <run-id>"
echo "Or: $PYTHON -m scripts.auto_enrich --run-id <run-id>"
