# Pipeline field protection (DaData as source of truth)

- **Date**: 2026-03-25
- **Git commit (main)**: `185d323`
- **Git commit (feature)**: `33548c6`
- **Scope**: `backend/` (Core internal import), `ai-pipeline/harvester/` (nightly harvest payload + DaData merge)
- **Primary reference**: `docs/Navigator_Core_Model_and_API.md`

## Problem statement

The nightly harvest pipeline updated existing organizations by sending a full “snapshot” payload into Core, and Core applied `Organization::update($attributes)` without field-level protection. This could:

- overwrite already confirmed/verified data (especially legal requisites);
- downgrade `approved` organizations due to a low-confidence LLM run;
- ignore venue updates once `organization_venues` had any rows (no add/update behavior for re-crawls).

## Goals

- Continuously refresh data from crawls **without damaging already confirmed fields**, especially those confirmed by DaData.
- Make updates safer and more idempotent (skip no-op updates).
- Allow adding new DaData-backed venues on re-crawls while preserving existing verified venues.

## Implemented changes

### 1) Core: field-level protection + idempotency

**DB**
- Added `organizations.verified_fields` (jsonb) and `organizations.content_hash` (varchar 32).

**Import pipeline**
- `POST /api/internal/import/organizer` now accepts optional `verified_fields` and `content_hash`.
- Added `App\Services\Import\ImportMergeService`:
  - protects `inn`, `ogrn`, `title`, `short_title` if already verified in DB and incoming payload is not marked verified for that field;
  - null-safety: prevents empty incoming values from overwriting non-empty DB values;
  - merges organizer contacts as a unique union (phones/emails), not a destructive replace;
  - status guard: prevents automatic downgrades of `approved` organizations (`approved` stays `approved`; `approved` + incoming `rejected` becomes `pending_review`).
- Idempotency: if incoming `content_hash` equals stored `organizations.content_hash`, Core skips the update.

**Venues**
- Existing orgs: Core now adds **only new venues with `fias_id`** (not already present), and never removes existing `fias_id` venues.
- New orgs: attaches all incoming venues as before.

**Classification**
- On update: uses additive sync (`syncWithoutDetaching`) to avoid deleting previously attached codes.
- On create: keeps replacing behavior (`sync`) as before.

### 2) Harvester: DaData party lookup in nightly harvest + verified tags

- `run_organization_harvest` now supports `enrich_party` (default `True`).
- Nightly harvest uses DaData:
  - if LLM produced `inn` → `find_party_by_id(inn)` (exact match);
  - else → `suggest_party(title)` (fuzzy match).
- If DaData returns a party, harvester merges party data into the payload via a shared module and sends:
  - `verified_fields` map (e.g. `{"inn":"dadata","ogrn":"dadata","title":"dadata"}`).

### 3) Harvester: null-safety + content hash at payload level

- `to_core_import_payload` omits empty `inn`/`ogrn`/`short_title` fields to prevent accidental clearing.
- Payload now includes `content_hash` (sha256 truncated) derived from key fields.

### 4) Backfill: verified_fields for existing records

- Added artisan command: `organizations:backfill-verified-fields`
  - checks approved orgs with INN/OGRN against DaData `findById/party`;
  - sets `verified_fields` accordingly;
  - supports `--limit` and `--dry-run`.

## Testing

**Backend**
- Added feature tests for:
  - verified `inn` not overwritten by non-verified payload;
  - `approved` status not downgraded;
  - venues with `fias_id` preserved; new `fias_id` venues appended;
  - additive classification on update;
  - `content_hash` skipping update.

**Harvester**
- Added unit tests for:
  - null-safety behavior (field omission);
  - DaData merge behavior and returned `verified_fields`;
  - content hash stability and change detection.

## Operational notes

- DaData free tier (10K/day) is sufficient to enable party lookup on nightly runs.
- The backfill command can be run gradually using `--limit` to control rate.

## Files changed (high level)

- Core:
  - `backend/app/Http/Controllers/Internal/ImportController.php`
  - `backend/app/Services/Import/ImportMergeService.php`
  - `backend/app/Console/Commands/BackfillVerifiedFieldsCommand.php`
  - `backend/app/Models/Organization.php`
  - `backend/database/schema/pgsql-schema.sql`
  - `backend/tests/Feature/Api/Internal/ImportFieldProtectionTest.php`
- Harvester:
  - `ai-pipeline/harvester/harvest/run_organization_harvest.py`
  - `ai-pipeline/harvester/processors/organization_processor.py`
  - `ai-pipeline/harvester/enrichment/dadata_merge.py`
  - `ai-pipeline/harvester/search/enrichment_pipeline.py`
  - `ai-pipeline/harvester/tests/test_field_protection.py`
  - `ai-pipeline/harvester/tests/test_payload_builder.py`

