<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Cleanup command to remove WordPress migration data from Navigator Core database.
 *
 * Removes all data created by the navigator:migrate-from-wp-base command,
 * including organizations, venues, organizers, pivot relationships, and articles.
 */
class CleanupWpMigrationDataCommand extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'navigator:cleanup-wp-migration-data
                            {--force : Force cleanup without confirmation}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Remove all data migrated from WordPress (organizations, venues, organizers, articles)';

    /**
     * Execute the console command.
     */
    public function handle(): int
    {
        if (! $this->option('force')) {
            if (! $this->confirm('This will delete all WordPress migration data. Continue?', false)) {
                $this->info('Cleanup cancelled.');

                return Command::SUCCESS;
            }
        }

        $this->info('Starting cleanup of WordPress migration data...');
        $this->newLine();

        try {
            DB::beginTransaction();

            // Count before deletion for statistics
            $stats = [
                'organizations' => DB::table('organizations')->count(),
                'venues' => DB::table('venues')->count(),
                'organizers' => DB::table('organizers')->count(),
                'articles' => DB::table('articles')->count(),
            ];

            // Delete in order of dependencies
            $this->info('Deleting pivot relationships...');
            DB::table('organization_venues')->delete();
            DB::table('event_venues')->delete();
            DB::table('organization_thematic_categories')->delete();
            DB::table('organization_organization_types')->delete();
            DB::table('organization_specialist_profiles')->delete();
            DB::table('organization_services')->delete();
            DB::table('event_event_categories')->delete();

            $this->info('Deleting organizers...');
            DB::table('organizers')->delete();

            $this->info('Deleting venues...');
            DB::table('venues')->delete();

            $this->info('Deleting organizations...');
            DB::table('organizations')->delete();

            $this->info('Deleting articles (WP migration does not tag them; all articles removed for clean re-run)...');
            DB::table('articles')->delete();

            $this->info('Deleting legacy source record...');
            DB::table('sources')
                ->where('base_url', 'wordpress-legacy')
                ->delete();

            DB::commit();

            $this->newLine();
            $this->info('Cleanup completed successfully!');
            $this->newLine();
            $this->table(
                ['Entity', 'Deleted'],
                [
                    ['Organizations', $stats['organizations']],
                    ['Venues', $stats['venues']],
                    ['Organizers', $stats['organizers']],
                    ['Articles', $stats['articles']],
                ]
            );

            return Command::SUCCESS;
        } catch (\Exception $e) {
            DB::rollBack();
            $this->error("Cleanup failed: {$e->getMessage()}");

            return Command::FAILURE;
        }
    }
}
