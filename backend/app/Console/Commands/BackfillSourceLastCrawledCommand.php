<?php

namespace App\Console\Commands;

use App\Models\Source;
use Illuminate\Console\Command;

/**
 * Backfill last_crawled_at and last_status for sources that were already processed
 * (171 broken URLs + sources created during auto_enrich run).
 *
 * Reads source IDs from harvester data files and runs a single UPDATE.
 * Writes an audit JSON with the list of IDs before updating (for rollback/verification).
 */
class BackfillSourceLastCrawledCommand extends Command
{
    protected $signature = 'sources:backfill-last-crawled
                            {--data-dir= : Path to harvester data dir (default: ../ai-pipeline/harvester/data from project root)}
                            {--progress-file= : Path to progress.jsonl (default: data-dir/runs/2026-02-25_no_sources/progress.jsonl)}
                            {--dry-run : Only collect IDs and write audit file, do not UPDATE}
                            {--audit= : Path to write audit JSON (default: data-dir/backfill_source_ids_<date>.json)}';

    protected $description = 'Backfill last_crawled_at and last_status for sources from harvester result files';

    public function handle(): int
    {
        $dataDir = $this->option('data-dir') ?: base_path('../ai-pipeline/harvester/data');
        $progressFile = $this->option('progress-file') ?: $dataDir.'/runs/2026-02-25_no_sources/progress.jsonl';
        $dryRun = (bool) $this->option('dry-run');
        $auditPath = $this->option('audit') ?: $dataDir.'/backfill_source_ids_'.now()->format('Y-m-d').'.json';

        $ids = [];

        $auto171 = $dataDir.'/results_171_merged_auto.json';
        if (is_file($auto171)) {
            $data = json_decode(file_get_contents($auto171), true);
            if (is_array($data)) {
                foreach ($data as $row) {
                    if (! empty($row['source_id']) && $this->isUuid($row['source_id'])) {
                        $ids[$row['source_id']] = true;
                    }
                }
                $this->info("From results_171_merged_auto.json: ".count($data)." rows, ".count($ids)." unique IDs so far.");
            }
        } else {
            $this->warn("File not found: {$auto171}");
        }

        $review171 = $dataDir.'/results_171_merged_review_review_ready.json';
        if (is_file($review171)) {
            $data = json_decode(file_get_contents($review171), true);
            if (is_array($data)) {
                $before = count($ids);
                foreach ($data as $row) {
                    if (! empty($row['approved']) && ! empty($row['source_id']) && $this->isUuid($row['source_id'])) {
                        $ids[$row['source_id']] = true;
                    }
                }
                $this->info("From results_171_merged_review_review_ready.json (approved): +".(count($ids) - $before)." IDs.");
            }
        } else {
            $this->warn("File not found: {$review171}");
        }

        if (is_file($progressFile)) {
            $before = count($ids);
            $lines = file($progressFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            foreach ($lines as $line) {
                $row = json_decode($line, true);
                if (is_array($row) && ! empty($row['source_id_created']) && $this->isUuid($row['source_id_created'])) {
                    $ids[$row['source_id_created']] = true;
                }
            }
            $this->info("From progress.jsonl: +".(count($ids) - $before)." IDs.");
        } else {
            $this->warn("File not found: {$progressFile}");
        }

        $idList = array_keys($ids);
        if (empty($idList)) {
            $this->warn('No source IDs collected. Check data-dir and file paths.');
            return self::FAILURE;
        }

        $idList = array_values(array_unique($idList));
        $this->info('Total unique source IDs to update: '.count($idList));

        $audit = [
            'created_at' => now()->toIso8601String(),
            'dry_run' => $dryRun,
            'source_ids' => $idList,
            'count' => count($idList),
            'sources' => [
                'results_171_merged_auto.json',
                'results_171_merged_review_review_ready.json (approved)',
                'progress.jsonl (source_id_created)',
            ],
        ];

        $auditDir = dirname($auditPath);
        if (! is_dir($auditDir)) {
            if (! mkdir($auditDir, 0755, true)) {
                $this->error("Cannot create directory: {$auditDir}");
                return self::FAILURE;
            }
        }
        file_put_contents($auditPath, json_encode($audit, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
        $this->info("Audit file written: {$auditPath}");

        if ($dryRun) {
            $this->info('Dry run: no database update performed.');
            return self::SUCCESS;
        }

        $updated = Source::whereIn('id', $idList)->update([
            'last_crawled_at' => now(),
            'last_status' => 'success',
            'updated_at' => now(),
        ]);

        $this->info("Updated {$updated} source(s).");
        return self::SUCCESS;
    }

    private function isUuid(string $s): bool
    {
        return (bool) preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i', $s);
    }
}
