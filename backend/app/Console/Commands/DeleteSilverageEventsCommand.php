<?php

namespace App\Console\Commands;

use App\Models\Event;
use App\Models\Organization;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Delete all events imported from Silver Age (platform organizer).
 * Use before re-importing with updated pipeline (event_ingestion, date parsing, classification).
 *
 * @see ai-pipeline/harvester/docs/event_ingestion_pipeline.md
 */
class DeleteSilverageEventsCommand extends Command
{
    protected $signature = 'navigator:delete-silverage-events
                            {--dry-run : List events only, do not delete}
                            {--force : Skip confirmation}
                            {--source-references= : Comma-separated source_reference list; if set, only these events are deleted}';

    protected $description = 'Delete events belonging to Silver Age platform organizer (source_reference=silverage_platform)';

    public function handle(): int
    {
        $org = Organization::where('source_reference', 'silverage_platform')->first();
        if (! $org) {
            $this->warn('No organization with source_reference=silverage_platform found. Nothing to delete.');

            return self::SUCCESS;
        }

        $organizer = $org->organizer;
        if (! $organizer) {
            $this->warn('Organization has no linked organizer. Nothing to delete.');

            return self::SUCCESS;
        }

        $refsOption = $this->option('source-references');
        $refs = $refsOption
            ? array_values(array_filter(array_map('trim', explode(',', $refsOption))))
            : [];

        $query = $organizer->events()->with('instances');
        if ($refs !== []) {
            $query->whereIn('source_reference', $refs);
            $this->info('Filtering by source_reference: '.implode(', ', $refs));
        }
        $events = $query->get();
        $count = $events->count();
        if ($count === 0) {
            $this->info('No events found for Silver Age platform. Nothing to delete.');

            return self::SUCCESS;
        }

        $this->info("Found {$count} event(s) for organizer {$organizer->id} (Silver Age platform).");
        if ($this->option('dry-run')) {
            foreach ($events as $e) {
                $this->line("  - [{$e->id}] {$e->title}");
            }
            $this->info('Dry run — no changes made.');

            return self::SUCCESS;
        }

        if (! $this->option('force') && ! $this->confirm("Delete {$count} event(s) and their instances?", false)) {
            $this->info('Cancelled.');

            return self::SUCCESS;
        }

        $deleted = 0;
        DB::transaction(function () use ($events, &$deleted) {
            foreach ($events as $event) {
                $event->instances()->delete();
                $event->delete();
                $deleted++;
            }
        });

        $this->info("Deleted {$deleted} event(s) and their instances.");

        return self::SUCCESS;
    }
}
