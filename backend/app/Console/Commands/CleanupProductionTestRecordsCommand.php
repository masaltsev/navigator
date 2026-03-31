<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Models\Organizer;
use App\Models\ParseProfile;
use App\Models\Source;
use App\Models\Venue;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Prunes obvious automated-test / fixture rows that landed on production:
 * sources with example.com & similar URLs, matching organizations/organizers,
 * and venues whose address contains "Тестовая" and are not tied to any active organization.
 */
class CleanupProductionTestRecordsCommand extends Command
{
    private const ORGANIZER_TYPE = 'Organization';

    protected $signature = 'db:cleanup-test-records
                            {--dry-run : List counts and IDs without deleting}
                            {--force : Actually soft-delete (ignored if dry-run)}';

    protected $description = 'Remove test/fixture organizations, sources, and orphan test venues from production-like data';

    /** PostgreSQL: URLs used by API/feature tests and harvester fixtures. */
    private function sourceUrlPatternSql(): string
    {
        return <<<'SQL'
            base_url ~* 'example\.com|due-test-|show-test\.example|last-crawled-test|patch-before\.example|registry-fpg\.example|existing\.example|other\.example|new-url\.example'
            OR base_url ~* '^https://vk\.com/(smart_test|test_geo)'
            SQL;
    }

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $force = (bool) $this->option('force');

        if (! $dryRun && ! $force) {
            $this->error('Refusing to modify data without --force. Use --dry-run to preview.');

            return self::FAILURE;
        }

        $sourceIds = $this->testSourceIds();
        $organizerIdsFromSources = $this->organizerIdsForSources($sourceIds);
        $orgIdsFromOrganizers = $this->organizationIdsForOrganizers($organizerIdsFromSources);
        $orgIdsByTitle = $this->testOrganizationIdsByTitle();
        $organizationIds = $orgIdsFromOrganizers->merge($orgIdsByTitle)->unique()->values();

        $organizerIdsForOrgs = $this->organizerIdsForOrganizations($organizationIds);
        $organizerIds = $organizerIdsFromSources->merge($organizerIdsForOrgs)->unique()->values();

        $venueIds = $this->testVenueIdsToPrune($organizationIds);

        $this->info('Planned actions:');
        $this->line('  parse_profiles (hard delete): '.$this->parseProfileCountForSources($sourceIds));
        $this->line('  sources (soft delete):        '.$sourceIds->count());
        $this->line('  organizations (soft delete):  '.$organizationIds->count());
        $this->line('  organizers (soft delete):     '.$organizerIds->count());
        $this->line('  venues (soft delete):           '.$venueIds->count());

        if ($dryRun) {
            $this->warn('Dry run — no changes.');

            return self::SUCCESS;
        }

        DB::transaction(function () use ($sourceIds, $organizationIds, $organizerIds, $venueIds) {
            if ($sourceIds->isNotEmpty()) {
                ParseProfile::query()->whereIn('source_id', $sourceIds)->delete();
                Source::query()->whereIn('id', $sourceIds)->delete();
            }
            if ($organizationIds->isNotEmpty()) {
                Organization::query()->whereIn('id', $organizationIds)->delete();
            }
            if ($organizerIds->isNotEmpty()) {
                Organizer::query()->whereIn('id', $organizerIds)->delete();
            }
            if ($venueIds->isNotEmpty()) {
                Venue::query()->whereIn('id', $venueIds)->delete();
            }
        });

        $this->info('Done.');

        return self::SUCCESS;
    }

    /**
     * @return \Illuminate\Support\Collection<int, string>
     */
    private function testSourceIds(): \Illuminate\Support\Collection
    {
        return DB::table('sources')
            ->whereNull('deleted_at')
            ->whereRaw('('.$this->sourceUrlPatternSql().')')
            ->pluck('id');
    }

    /**
     * @param  \Illuminate\Support\Collection<int, mixed>  $sourceIds
     */
    private function parseProfileCountForSources(\Illuminate\Support\Collection $sourceIds): int
    {
        if ($sourceIds->isEmpty()) {
            return 0;
        }

        return (int) ParseProfile::query()->whereIn('source_id', $sourceIds)->count();
    }

    /**
     * @param  \Illuminate\Support\Collection<int, mixed>  $sourceIds
     * @return \Illuminate\Support\Collection<int, string>
     */
    private function organizerIdsForSources(\Illuminate\Support\Collection $sourceIds): \Illuminate\Support\Collection
    {
        if ($sourceIds->isEmpty()) {
            return collect();
        }

        return DB::table('sources')
            ->whereIn('id', $sourceIds)
            ->whereNotNull('organizer_id')
            ->pluck('organizer_id')
            ->unique()
            ->values();
    }

    /**
     * @param  \Illuminate\Support\Collection<int, mixed>  $organizerIds
     * @return \Illuminate\Support\Collection<int, string>
     */
    private function organizationIdsForOrganizers(\Illuminate\Support\Collection $organizerIds): \Illuminate\Support\Collection
    {
        if ($organizerIds->isEmpty()) {
            return collect();
        }

        return DB::table('organizers')
            ->whereIn('id', $organizerIds)
            ->where('organizable_type', self::ORGANIZER_TYPE)
            ->whereNull('deleted_at')
            ->pluck('organizable_id');
    }

    /**
     * @return \Illuminate\Support\Collection<int, string>
     */
    private function testOrganizationIdsByTitle(): \Illuminate\Support\Collection
    {
        return DB::table('organizations')
            ->whereNull('deleted_at')
            ->where(function ($q) {
                $q->where('title', 'Тестовая организация')
                    ->orWhere('title', 'ilike', 'Example Domain%')
                    ->orWhere('title', 'ilike', '%Lookup by Source ID Org%')
                    ->orWhere('source_reference', 'ilike', '%example.com%');
            })
            ->pluck('id');
    }

    /**
     * @param  \Illuminate\Support\Collection<int, mixed>  $organizationIdsToDelete
     * @return \Illuminate\Support\Collection<int, string>
     */
    private function organizerIdsForOrganizations(\Illuminate\Support\Collection $organizationIdsToDelete): \Illuminate\Support\Collection
    {
        if ($organizationIdsToDelete->isEmpty()) {
            return collect();
        }

        return DB::table('organizers')
            ->where('organizable_type', self::ORGANIZER_TYPE)
            ->whereIn('organizable_id', $organizationIdsToDelete)
            ->whereNull('deleted_at')
            ->pluck('id');
    }

    /**
     * Venues with "Тестовая" in the address safe to remove: no active organization remains
     * outside the set we are deleting (avoids removing a venue still used by a real org).
     *
     * @param  \Illuminate\Support\Collection<int, mixed>  $organizationIdsToDelete
     * @return \Illuminate\Support\Collection<int, string>
     */
    private function testVenueIdsToPrune(\Illuminate\Support\Collection $organizationIdsToDelete): \Illuminate\Support\Collection
    {
        $ids = $organizationIdsToDelete->map(fn ($id) => (string) $id)->all();

        return DB::table('venues as v')
            ->whereNull('v.deleted_at')
            ->where('v.address_raw', 'ilike', '%Тестовая%')
            ->whereNotExists(function ($q) use ($ids) {
                $q->select(DB::raw(1))
                    ->from('organization_venues as ov')
                    ->join('organizations as o', 'o.id', '=', 'ov.organization_id')
                    ->whereColumn('ov.venue_id', 'v.id')
                    ->whereNull('o.deleted_at');
                if ($ids !== []) {
                    $q->whereNotIn('o.id', $ids);
                }
            })
            ->pluck('v.id');
    }
}
