<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Services\Import\OrganizationDuplicateMergeService;
use App\Support\SuspiciousOrgsExactTitleMergeGroupExtractor;
use Illuminate\Console\Command;

class MergeExactTitleDuplicateOrganizationsCommand extends Command
{
    protected $signature = 'db:merge-exact-title-org-duplicates
                            {--path= : Path to suspicious-orgs.json (default: base_path/suspicious-orgs.json)}
                            {--dry-run : List merges without changing data}
                            {--force : Execute merges (required when not dry-run)}';

    protected $description = 'Merge exact-title duplicate organizations from suspicious-orgs report into canonical INN/OGRN records';

    public function handle(OrganizationDuplicateMergeService $mergeService): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $force = (bool) $this->option('force');

        if (! $dryRun && ! $force) {
            $this->error('Use --dry-run to preview or --force to execute.');

            return self::FAILURE;
        }

        $path = $this->option('path') ?: base_path('suspicious-orgs.json');
        if (! is_readable($path)) {
            $this->error("File not readable: {$path}");

            return self::FAILURE;
        }

        try {
            $pairs = SuspiciousOrgsExactTitleMergeGroupExtractor::mergePairsFromReportFile($path);
        } catch (\InvalidArgumentException $e) {
            $this->error($e->getMessage());

            return self::FAILURE;
        }

        $this->info('Exact-title merge pairs: '.count($pairs));

        $merged = 0;
        $skipped = 0;

        foreach ($pairs as $p) {
            $dupId = $p['duplicate_id'];
            $canonId = $p['canonical_id'];

            $canon = Organization::query()->whereKey($canonId)->whereNull('deleted_at')->first();
            if (! $canon) {
                $this->warn("Skip: canonical {$canonId} not found or deleted");
                $skipped++;

                continue;
            }

            $dup = Organization::query()->whereKey($dupId)->whereNull('deleted_at')->first();
            if (! $dup) {
                if (Organization::query()->onlyTrashed()->whereKey($dupId)->exists()) {
                    $this->line("  (skip: duplicate {$dupId} already soft-deleted)");
                } else {
                    $this->warn("Skip: duplicate {$dupId} not found");
                }
                $skipped++;

                continue;
            }

            if (! $this->organizationHasLegalId($canon)) {
                $this->warn("Skip: canonical {$canonId} has no INN/OGRN");
                $skipped++;

                continue;
            }

            if ($this->organizationHasLegalId($dup)) {
                $this->warn("Skip: duplicate {$dupId} has INN/OGRN (resolve manually)");
                $skipped++;

                continue;
            }

            $this->line("  {$dupId} → {$canonId} | {$p['norm_title']}");

            if ($dryRun) {
                continue;
            }

            $mergeService->mergeDuplicateIntoCanonical($canon, $dup);
            $merged++;
        }

        if ($dryRun) {
            $this->warn('Dry run — no changes.');
        } else {
            $this->info("Merged {$merged} duplicate(s); skipped {$skipped}.");
        }

        return self::SUCCESS;
    }

    private function organizationHasLegalId(Organization $org): bool
    {
        $inn = $org->inn !== null ? trim((string) $org->inn) : '';
        $ogrn = $org->ogrn !== null ? trim((string) $org->ogrn) : '';

        return $inn !== '' || $ogrn !== '';
    }
}
