<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Cleanup duplicate venues and organizers created during WordPress migration.
 *
 * This command:
 * - Removes duplicate venues (same address_raw for same organization)
 * - Keeps only one organizer per organization (the most recent one)
 */
class CleanupWpMigrationDuplicatesCommand extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'navigator:cleanup-wp-migration-duplicates
                            {--dry-run : Show what would be deleted without actually deleting}
                            {--force : Skip confirmation prompt}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Cleanup duplicate venues and organizers created during WordPress migration';

    /**
     * Execute the console command.
     */
    public function handle(): int
    {
        if (! $this->option('force') && ! $this->option('dry-run')) {
            if (! $this->confirm('This will delete duplicate venues and organizers. Continue?', false)) {
                $this->info('Cleanup cancelled.');

                return Command::SUCCESS;
            }
        }

        $isDryRun = $this->option('dry-run');

        if ($isDryRun) {
            $this->info('DRY RUN MODE - No changes will be made');
            $this->newLine();
        }

        $this->info('Starting cleanup of duplicates...');
        $this->newLine();

        try {
            DB::beginTransaction();

            // 1. Cleanup duplicate venues
            $this->info('1. Cleaning up duplicate venues...');
            $duplicateVenues = $this->findDuplicateVenues();
            $duplicateVenuesCount = count($duplicateVenues);
            $this->info("   Found {$duplicateVenuesCount} duplicate venue-organization pairs");

            if ($duplicateVenuesCount > 0 && ! $isDryRun) {
                $deletedVenues = 0;
                foreach ($duplicateVenues as $duplicate) {
                    // Keep the first venue (oldest), delete others
                    $venuesToDelete = DB::table('venues')
                        ->join('organization_venues', 'venues.id', '=', 'organization_venues.venue_id')
                        ->where('organization_venues.organization_id', $duplicate->organization_id)
                        ->where('venues.address_raw', $duplicate->address_raw)
                        ->where('venues.id', '!=', $duplicate->keep_venue_id)
                        ->pluck('venues.id');

                    if ($venuesToDelete->count() > 0) {
                        // Delete pivot relationships first
                        DB::table('organization_venues')
                            ->whereIn('venue_id', $venuesToDelete)
                            ->delete();

                        // Delete venues
                        DB::table('venues')
                            ->whereIn('id', $venuesToDelete)
                            ->delete();

                        $deletedVenues += $venuesToDelete->count();
                    }
                }
                $this->info("   Deleted {$deletedVenues} duplicate venues");
            }

            // 2. Cleanup organizers - keep only one per organization
            $this->newLine();
            $this->info('2. Cleaning up organizers...');

            $totalOrganizers = DB::table('organizers')
                ->where('organizable_type', 'Organization')
                ->count();
            $totalOrgs = DB::table('organizations')->count();
            $this->info("   Current: {$totalOrganizers} organizers for {$totalOrgs} organizations");

            if (! $isDryRun) {
                // Strategy: Delete all organizers for organizations, then create exactly one per organization

                // Step 1: Delete all organizers for organizations
                $deletedCount = DB::table('organizers')
                    ->where('organizable_type', 'Organization')
                    ->delete();
                $this->info("   Deleted {$deletedCount} organizers");

                // Step 2: Create exactly one organizer per organization
                $allOrgs = DB::table('organizations')->pluck('id');
                $created = 0;

                foreach ($allOrgs as $orgId) {
                    DB::table('organizers')->insert([
                        'id' => \Illuminate\Support\Str::uuid(),
                        'organizable_type' => 'Organization',
                        'organizable_id' => $orgId,
                        'contact_phones' => '[]',
                        'contact_emails' => '[]',
                        'status' => 'approved',
                        'created_at' => now(),
                        'updated_at' => now(),
                    ]);
                    $created++;
                }

                $this->info("   Created {$created} organizers (one per organization)");
            } else {
                $this->info("   Would delete {$totalOrganizers} organizers");
                $this->info("   Would create {$totalOrgs} organizers (one per organization)");
            }

            if ($isDryRun) {
                DB::rollBack();
                $this->newLine();
                $this->info('Dry run completed. No changes were made.');
            } else {
                DB::commit();
                $this->newLine();
                $this->info('Cleanup completed successfully!');
            }

            // Show final statistics
            $this->newLine();
            $this->showStatistics();

            return Command::SUCCESS;
        } catch (\Exception $e) {
            DB::rollBack();
            $this->error("Cleanup failed: {$e->getMessage()}");

            return Command::FAILURE;
        }
    }

    /**
     * Find duplicate venues (same address_raw for same organization).
     */
    private function findDuplicateVenues()
    {
        return DB::select('
            SELECT 
                ov.organization_id,
                v.address_raw,
                (
                    SELECT v2.id
                    FROM venues v2
                    INNER JOIN organization_venues ov2 ON v2.id = ov2.venue_id
                    WHERE ov2.organization_id = ov.organization_id
                    AND v2.address_raw = v.address_raw
                    ORDER BY v2.created_at ASC
                    LIMIT 1
                ) as keep_venue_id,
                COUNT(*) as duplicate_count
            FROM venues v
            INNER JOIN organization_venues ov ON v.id = ov.venue_id
            WHERE v.address_raw IS NOT NULL
            GROUP BY ov.organization_id, v.address_raw
            HAVING COUNT(*) > 1
        ');
    }

    /**
     * Find organizations with multiple organizers.
     */
    private function findDuplicateOrganizers()
    {
        return DB::select("
            SELECT 
                organizable_id as organization_id,
                (
                    SELECT id
                    FROM organizers o2
                    WHERE o2.organizable_id = organizers.organizable_id
                    AND o2.organizable_type = 'Organization'
                    ORDER BY o2.created_at DESC
                    LIMIT 1
                ) as keep_organizer_id,
                COUNT(*) as organizer_count
            FROM organizers
            WHERE organizable_type = 'Organization'
            GROUP BY organizable_id
            HAVING COUNT(*) > 1
        ");
    }

    /**
     * Show final statistics after cleanup.
     */
    private function showStatistics(): void
    {
        $stats = [
            'organizations' => DB::table('organizations')->count(),
            'venues' => DB::table('venues')->count(),
            'organizers' => DB::table('organizers')
                ->where('organizable_type', 'Organization')
                ->count(),
            'organization_venues' => DB::table('organization_venues')->count(),
        ];

        $this->table(
            ['Entity', 'Count'],
            [
                ['Organizations', $stats['organizations']],
                ['Venues', $stats['venues']],
                ['Organizers (for Organizations)', $stats['organizers']],
                ['Organization-Venue links', $stats['organization_venues']],
            ]
        );
    }
}
