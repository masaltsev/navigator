<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * One-off command: collect Navigator Core DB statistics for reporting.
 * Outputs JSON to stdout for use in reports (see docs/Navigator_Core_Model_and_API.md).
 */
class DatabaseStatsReportCommand extends Command
{
    protected $signature = 'db:stats-report';

    protected $description = 'Output DB statistics as JSON for Navigator Core analysis report';

    private const ORGANIZER_TYPE = 'Organization';

    public function handle(): int
    {
        $stats = [
            'organizations' => $this->organizationStats(),
            'events' => $this->eventStats(),
            'sources' => $this->sourceStats(),
            'venues' => $this->venueStats(),
        ];

        $this->line(json_encode($stats, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

        return self::SUCCESS;
    }

    /**
     * @return array<string, mixed>
     */
    private function organizationStats(): array
    {
        $total = (int) DB::table('organizations')->whereNull('deleted_at')->count();
        $approved = (int) DB::table('organizations')->whereNull('deleted_at')->where('status', 'approved')->count();

        $approvedWithOrganizer = (int) DB::table('organizations')
            ->whereNull('organizations.deleted_at')
            ->where('organizations.status', 'approved')
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organizers')
                    ->whereColumn('organizers.organizable_id', 'organizations.id')
                    ->where('organizers.organizable_type', self::ORGANIZER_TYPE)
                    ->whereNull('organizers.deleted_at');
            })
            ->count();

        $approvedWithSourceKind = [];
        foreach (['org_website', 'vk_group', 'tg_channel', 'ok_group'] as $kind) {
            $approvedWithSourceKind[$kind] = (int) DB::table('organizations')
                ->whereNull('organizations.deleted_at')
                ->where('organizations.status', 'approved')
                ->whereExists(function ($q) use ($kind) {
                    $q->select(DB::raw(1))
                        ->from('organizers')
                        ->join('sources', 'sources.organizer_id', '=', 'organizers.id')
                        ->whereColumn('organizers.organizable_id', 'organizations.id')
                        ->where('organizers.organizable_type', self::ORGANIZER_TYPE)
                        ->whereNull('organizers.deleted_at')
                        ->whereNull('sources.deleted_at')
                        ->where('sources.kind', $kind);
                })
                ->count();
        }

        $approvedWithThematicCategory = (int) DB::table('organizations')
            ->whereNull('organizations.deleted_at')
            ->where('organizations.status', 'approved')
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organization_thematic_categories')
                    ->whereColumn('organization_thematic_categories.organization_id', 'organizations.id');
            })
            ->count();

        $approvedWithAtLeastOneVenue = (int) DB::table('organizations')
            ->whereNull('organizations.deleted_at')
            ->where('organizations.status', 'approved')
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organization_venues')
                    ->whereColumn('organization_venues.organization_id', 'organizations.id');
            })
            ->count();

        $approvedWithAtLeastOneSource = (int) DB::table('organizations')
            ->whereNull('organizations.deleted_at')
            ->where('organizations.status', 'approved')
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organizers')
                    ->join('sources', 'sources.organizer_id', '=', 'organizers.id')
                    ->whereColumn('organizers.organizable_id', 'organizations.id')
                    ->where('organizers.organizable_type', self::ORGANIZER_TYPE)
                    ->whereNull('organizers.deleted_at')
                    ->whereNull('sources.deleted_at');
            })
            ->count();

        $idealOrganizations = (int) DB::table('organizations')
            ->whereNull('organizations.deleted_at')
            ->where('organizations.status', 'approved')
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organizers')
                    ->join('sources', 'sources.organizer_id', '=', 'organizers.id')
                    ->whereColumn('organizers.organizable_id', 'organizations.id')
                    ->where('organizers.organizable_type', self::ORGANIZER_TYPE)
                    ->whereNull('organizers.deleted_at')
                    ->whereNull('sources.deleted_at');
            })
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organization_venues')
                    ->whereColumn('organization_venues.organization_id', 'organizations.id');
            })
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organization_thematic_categories')
                    ->whereColumn('organization_thematic_categories.organization_id', 'organizations.id');
            })
            ->count();

        $approvedWithoutThematicCategoryAndWithoutSource = (int) DB::table('organizations')
            ->whereNull('organizations.deleted_at')
            ->where('organizations.status', 'approved')
            ->whereNotExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organization_thematic_categories')
                    ->whereColumn('organization_thematic_categories.organization_id', 'organizations.id');
            })
            ->whereNotExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organizers')
                    ->join('sources', 'sources.organizer_id', '=', 'organizers.id')
                    ->whereColumn('organizers.organizable_id', 'organizations.id')
                    ->where('organizers.organizable_type', self::ORGANIZER_TYPE)
                    ->whereNull('organizers.deleted_at')
                    ->whereNull('sources.deleted_at');
            })
            ->count();

        return [
            'total' => $total,
            'approved' => $approved,
            'approved_with_organizer' => $approvedWithOrganizer,
            'approved_with_source_by_kind' => $approvedWithSourceKind,
            'approved_with_thematic_category' => $approvedWithThematicCategory,
            'approved_with_at_least_one_venue' => $approvedWithAtLeastOneVenue,
            'approved_with_at_least_one_source' => $approvedWithAtLeastOneSource,
            'ideal_organizations' => $idealOrganizations,
            'approved_without_thematic_category_and_without_source' => $approvedWithoutThematicCategoryAndWithoutSource,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function eventStats(): array
    {
        $total = (int) DB::table('events')->whereNull('deleted_at')->count();
        $approved = (int) DB::table('events')->whereNull('deleted_at')->where('status', 'approved')->count();
        $instancesScheduled = (int) DB::table('event_instances')->where('status', 'scheduled')->count();

        return [
            'total' => $total,
            'approved' => $approved,
            'event_instances_scheduled' => $instancesScheduled,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function sourceStats(): array
    {
        $total = (int) DB::table('sources')->whereNull('deleted_at')->count();

        $duplicateBaseUrl = DB::selectOne('
            SELECT COUNT(*) AS cnt FROM (
                SELECT base_url, COUNT(*) AS c
                FROM sources
                WHERE deleted_at IS NULL
                GROUP BY base_url
                HAVING COUNT(*) > 1
            ) sub
        ');
        $potentialDuplicateSources = (int) ($duplicateBaseUrl->cnt ?? 0);

        $rowsWithSameUrl = DB::selectOne('
            SELECT COALESCE(SUM(c - 1), 0)::int AS extra
            FROM (
                SELECT base_url, COUNT(*) AS c
                FROM sources
                WHERE deleted_at IS NULL
                GROUP BY base_url
                HAVING COUNT(*) > 1
            ) sub
        ');
        $potentialDuplicateRows = (int) ($rowsWithSameUrl->extra ?? 0);

        return [
            'total' => $total,
            'potential_duplicate_url_groups' => $potentialDuplicateSources,
            'potential_duplicate_rows' => $potentialDuplicateRows,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function venueStats(): array
    {
        $total = (int) DB::table('venues')->whereNull('deleted_at')->count();

        $duplicateAddress = DB::selectOne('
            SELECT COUNT(*) AS cnt FROM (
                SELECT address_raw, COUNT(*) AS c
                FROM venues
                WHERE deleted_at IS NULL
                GROUP BY address_raw
                HAVING COUNT(*) > 1
            ) sub
        ');
        $potentialDuplicateByAddress = (int) ($duplicateAddress->cnt ?? 0);

        $duplicateFias = DB::selectOne("
            SELECT COUNT(*) AS cnt FROM (
                SELECT fias_id, COUNT(*) AS c
                FROM venues
                WHERE deleted_at IS NULL AND fias_id IS NOT NULL AND fias_id != ''
                GROUP BY fias_id
                HAVING COUNT(*) > 1
            ) sub
        ");
        $potentialDuplicateByFias = (int) ($duplicateFias->cnt ?? 0);

        return [
            'total' => $total,
            'potential_duplicate_groups_by_address_raw' => $potentialDuplicateByAddress,
            'potential_duplicate_groups_by_fias_id' => $potentialDuplicateByFias,
        ];
    }
}
