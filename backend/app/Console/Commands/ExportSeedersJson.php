<?php

namespace App\Console\Commands;

use App\Models\OrganizationType;
use App\Models\OwnershipType;
use App\Models\Service;
use App\Models\SpecialistProfile;
use App\Models\ThematicCategory;
use Illuminate\Console\Command;

/**
 * Export active seeders to JSON for AI Pipeline (Harvester).
 * Run after db:seed. Output: ai-pipeline/harvester/seeders_data/
 */
class ExportSeedersJson extends Command
{
    protected $signature = 'seeders:export-json';

    protected $description = 'Export active seeders to JSON for AI Pipeline';

    public function handle(): int
    {
        $outputDir = base_path('../ai-pipeline/harvester/seeders_data');
        if (! is_dir($outputDir)) {
            mkdir($outputDir, 0755, true);
        }

        $categories = ThematicCategory::where('is_active', true)
            ->with('parent')
            ->get()
            ->map(fn ($cat) => [
                'id' => $cat->id,
                'code' => $cat->code,
                'name' => $cat->name,
                'is_active' => $cat->is_active,
                'parent_code' => $cat->parent?->code,
            ]);
        $this->writeJson($outputDir, 'thematic_categories.json', $categories->all());

        $this->exportFlat($outputDir, 'services.json', Service::class);
        $this->exportFlat($outputDir, 'organization_types.json', OrganizationType::class);
        $this->exportFlat($outputDir, 'specialist_profiles.json', SpecialistProfile::class);

        $ownership = OwnershipType::where('is_active', true)
            ->where('code', '!=', '151')
            ->get(['id', 'code', 'name', 'is_active'])
            ->map(fn ($m) => $m->toArray())
            ->all();
        $this->writeJson($outputDir, 'ownership_types.json', $ownership);

        $this->info('Seeders exported to ai-pipeline/harvester/seeders_data/');

        return self::SUCCESS;
    }

    private function exportFlat(string $dir, string $filename, string $model): void
    {
        $data = $model::where('is_active', true)
            ->get(['id', 'code', 'name', 'is_active'])
            ->map(fn ($m) => $m->toArray())
            ->all();
        $this->writeJson($dir, $filename, $data);
    }

    /**
     * @param  array<int, array<string, mixed>>  $data
     */
    private function writeJson(string $dir, string $filename, array $data): void
    {
        file_put_contents(
            $dir.'/'.$filename,
            json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
        );
    }
}
