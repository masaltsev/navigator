<?php

namespace App\Console\Commands;

use App\Models\OrganizationType;
use App\Models\Service;
use App\Models\SpecialistProfile;
use App\Models\ThematicCategory;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Find and remove duplicate terms in ontology tables (same name).
 * Deletes only duplicates that have zero relations (organizations, articles, pivots).
 */
class RemoveDuplicateOntologyTermsCommand extends Command
{
    protected $signature = 'navigator:remove-duplicate-ontology-terms
                            {--dry-run : List duplicates and usage, do not delete}
                            {--force : Skip confirmation}';

    protected $description = 'Remove duplicate thematic categories, services, organization types, specialist profiles (same name); only if not used in relations';

    public function handle(): int
    {
        $dryRun = $this->option('dry-run');
        if (! $this->option('force') && ! $dryRun && ! $this->confirm('Remove duplicate ontology terms (only those with no relations)?', false)) {
            $this->info('Cancelled.');

            return self::SUCCESS;
        }

        if ($dryRun) {
            $this->info('DRY RUN — no changes will be made.');
            $this->newLine();
        }

        $totalDeleted = 0;

        $totalDeleted += $this->processTable(
            'thematic_categories',
            ThematicCategory::class,
            fn (ThematicCategory $m) => $m->organizations()->count() + $m->articles()->count(),
            $dryRun
        );

        $totalDeleted += $this->processTable(
            'services',
            Service::class,
            fn (Service $m) => $m->organizations()->count() + $m->articles()->count(),
            $dryRun
        );

        $totalDeleted += $this->processTable(
            'organization_types',
            OrganizationType::class,
            fn (OrganizationType $m) => DB::table('organization_organization_types')->where('organization_type_id', $m->id)->count(),
            $dryRun
        );

        $totalDeleted += $this->processTable(
            'specialist_profiles',
            SpecialistProfile::class,
            fn (SpecialistProfile $m) => $m->organizations()->count(),
            $dryRun
        );

        $this->newLine();
        $this->info($dryRun ? 'Dry run complete.' : "Deleted {$totalDeleted} duplicate term(s).");

        return self::SUCCESS;
    }

    /**
     * @param  \Illuminate\Database\Eloquent\Model  $modelClass
     * @param  callable  $usageCount  (Model): int
     */
    private function processTable(string $tableName, string $modelClass, callable $usageCount, bool $dryRun): int
    {
        $this->info("Table: {$tableName}");

        $duplicatesByName = $modelClass::query()
            ->select('name', DB::raw('COUNT(*) as cnt'), DB::raw('MIN(code) as min_code'))
            ->groupBy('name')
            ->havingRaw('COUNT(*) > 1')
            ->pluck('min_code', 'name');

        if ($duplicatesByName->isEmpty()) {
            $this->line('  No duplicates by name.');
            $this->newLine();

            return 0;
        }

        $deleted = 0;
        foreach ($duplicatesByName as $name => $keepCode) {
            $candidates = $modelClass::where('name', $name)->orderBy('code')->get();
            $keep = $candidates->first(fn ($m) => $m->code === $keepCode);
            if (! $keep) {
                continue;
            }

            foreach ($candidates as $model) {
                if ($model->id === $keep->id) {
                    continue;
                }

                $usage = $usageCount($model);
                if ($usage > 0) {
                    $this->line("  SKIP id={$model->id} code={$model->code} \"{$name}\" — used in {$usage} relation(s).");

                    continue;
                }

                $this->line('  '.($dryRun ? 'Would delete' : 'Delete')." id={$model->id} code={$model->code} \"{$name}\" (0 relations).");
                if (! $dryRun) {
                    $model->delete();
                    $deleted++;
                } else {
                    $deleted++;
                }
            }
        }

        $this->newLine();

        return $dryRun ? 0 : $deleted;
    }
}
