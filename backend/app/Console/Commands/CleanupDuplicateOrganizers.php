<?php

namespace App\Console\Commands;

use App\Models\Organizer;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Cleanup duplicate organizers: keep only one organizer per organization.
 * For each organization with multiple organizers, keeps the oldest one (or one with data).
 */
class CleanupDuplicateOrganizers extends Command
{
    protected $signature = 'organizers:cleanup-duplicates
                            {--dry-run : Do not delete, only show planned deletions}
                            {--keep-oldest : Keep oldest organizer (by created_at), otherwise keep first by ID}';

    protected $description = 'Remove duplicate organizers, keeping only one per organization';

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $keepOldest = (bool) $this->option('keep-oldest');

        // Find organizations with multiple organizers
        $duplicates = DB::select(
            'SELECT organizable_id, COUNT(*) as cnt FROM organizers WHERE organizable_type = ? GROUP BY organizable_id HAVING COUNT(*) > 1',
            ['Organization']
        );

        if (empty($duplicates)) {
            $this->info('No duplicate organizers found.');

            return self::SUCCESS;
        }

        $this->info('Found '.count($duplicates).' organizations with multiple organizers.');

        $deleted = 0;
        $reassignedSources = 0;

        foreach ($duplicates as $dup) {
            $orgId = $dup->organizable_id;

            // Get all organizers for this organization
            $organizers = DB::table('organizers')
                ->where('organizable_type', 'Organization')
                ->where('organizable_id', $orgId)
                ->orderBy($keepOldest ? 'created_at' : 'id', 'asc')
                ->get(['id', 'created_at', 'contact_phones', 'contact_emails']);

            if ($organizers->isEmpty()) {
                continue;
            }

            // Keep the first one (oldest or first by ID)
            $keepId = $organizers->first()->id;
            $toDelete = $organizers->skip(1)->pluck('id')->toArray();

            if (empty($toDelete)) {
                continue;
            }

            // Reassign sources from deleted organizers to the kept one
            if (! $dryRun) {
                $sourcesUpdated = DB::table('sources')
                    ->whereIn('organizer_id', $toDelete)
                    ->update(['organizer_id' => $keepId]);
                $reassignedSources += $sourcesUpdated;
            }

            // Delete duplicate organizers
            if (! $dryRun) {
                DB::table('organizers')->whereIn('id', $toDelete)->delete();
            }

            $deleted += count($toDelete);

            if ($this->output->isVerbose()) {
                $this->line("  org_id={$orgId}: keeping {$keepId}, deleting ".count($toDelete).' duplicate(s)');
            }
        }

        $this->newLine();
        $this->info("Done. Deleted: {$deleted} duplicate organizers, reassigned sources: {$reassignedSources}.");

        return self::SUCCESS;
    }
}
