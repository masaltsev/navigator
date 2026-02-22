# Navigator Harvester (Phase 1)

Crawl4AI + DeepSeek pipeline for enriching `org_website` sources. Extracts structured organization data and aligns it with Navigator Core dictionaries.

## Requirements

- Python 3.12+
- [DeepSeek API key](https://platform.deepseek.com/) (for LLM extraction)
- After first run: seeders JSON in `seeders_data/` (see below)

## Setup

```bash
cd ai-pipeline/harvester
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
cp .env.example .env
# Edit .env: set DEEPSEEK_API_KEY
```

## Seeders (dictionaries)

Dictionaries are exported from Laravel. From the **backend** directory:

```bash
cd backend
php artisan seeders:export-json
```

This writes JSON files into `ai-pipeline/harvester/seeders_data/`. Run after any change to seeders or at least once before first crawl.

## Run single URL (CLI)

From `ai-pipeline/harvester`:

```bash
python -m scripts.run_single_url "https://example-org.gov.ru" --pretty
```

Output: JSON object conforming to `RawOrganizationData` (or an error object with `"error"` and `"url"`).

Environment:

- `DEEPSEEK_API_KEY` — required for LLM extraction
- `DEEPSEEK_MODEL` — optional, default `deepseek/deepseek-chat`
- `CRAWL4AI_HEADLESS` — optional, default `true`
- `CRAWL4AI_USER_AGENT` — optional

## Project layout

- `config/` — settings, LLM config, seeders loader
- `schemas/` — Pydantic models (extraction, navigator_core), CSS templates (Sprint 3)
- `strategies/` — strategy router, regex, CSS, LLM
- `prompts/` — system prompt stub, registry
- `scripts/` — CLI (run_single_url), later: generate_css_schema, seed_test_sources
- `enrichment/` — Sprint 2 (classifier, Dadata, confidence, payload_builder)
- `workers/` — Sprint 3 (Celery)
- `core_client/` — Sprint 2 (Core API client)
- `tests/` — unit and fixtures

## DoD Sprint 1

CLI accepts a URL and prints `RawOrganizationData` as JSON.

### Task 1.10 — live test on 5 URLs

1. Set `DEEPSEEK_API_KEY` in `.env` (or export in shell).
2. Install browser for Crawl4AI (one-time):  
   `cd ai-pipeline/harvester && .venv/bin/playwright install chromium`  
   (if `playwright` is on PATH from the venv).
3. Run on 5 real KCSON (or any org) URLs, e.g.:  
   `python -m scripts.run_single_url "https://..." --pretty`
4. Check output: valid `RawOrganizationData` JSON or error object with `"error"` and `"url"`.
