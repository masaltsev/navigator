<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Analyze dictionary links for organizations: thematic categories, specialist profiles,
 * services, ownership type, organization types.
 * Identifies problematic organizations without thematic category links.
 */
class AnalyzeOrganizationDictionaryLinks extends Command
{
    protected $signature = 'orgs:analyze-dictionary-links';

    protected $description = 'Analyze dictionary links for organizations and identify problematic ones';

    public function handle(): int
    {
        $total = DB::table('organizations')
            ->where('status', 'approved')
            ->whereNull('deleted_at')
            ->count();

        // Count organizations with each dictionary link
        $withThematic = DB::table('organizations')
            ->where('status', 'approved')
            ->whereNull('deleted_at')
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organization_thematic_categories')
                    ->whereColumn('organization_thematic_categories.organization_id', 'organizations.id');
            })
            ->count();

        $withSpecialistProfile = DB::table('organizations')
            ->where('status', 'approved')
            ->whereNull('deleted_at')
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organization_specialist_profiles')
                    ->whereColumn('organization_specialist_profiles.organization_id', 'organizations.id');
            })
            ->count();

        $withService = DB::table('organizations')
            ->where('status', 'approved')
            ->whereNull('deleted_at')
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organization_services')
                    ->whereColumn('organization_services.organization_id', 'organizations.id');
            })
            ->count();

        $withOwnershipType = DB::table('organizations')
            ->where('status', 'approved')
            ->whereNull('deleted_at')
            ->whereNotNull('ownership_type_id')
            ->count();

        $withOrganizationType = DB::table('organizations')
            ->where('status', 'approved')
            ->whereNull('deleted_at')
            ->whereExists(function ($q) {
                $q->select(DB::raw(1))
                    ->from('organization_organization_types')
                    ->whereColumn('organization_organization_types.organization_id', 'organizations.id');
            })
            ->count();

        $withoutThematic = $total - $withThematic;

        // Detailed breakdown: organizations with different combinations
        $stats = DB::select("
            SELECT 
                COUNT(*) as cnt,
                CASE WHEN EXISTS (SELECT 1 FROM organization_thematic_categories WHERE organization_id = o.id) THEN 1 ELSE 0 END as has_thematic,
                CASE WHEN EXISTS (SELECT 1 FROM organization_specialist_profiles WHERE organization_id = o.id) THEN 1 ELSE 0 END as has_specialist,
                CASE WHEN EXISTS (SELECT 1 FROM organization_services WHERE organization_id = o.id) THEN 1 ELSE 0 END as has_service,
                CASE WHEN o.ownership_type_id IS NOT NULL THEN 1 ELSE 0 END as has_ownership,
                CASE WHEN EXISTS (SELECT 1 FROM organization_organization_types WHERE organization_id = o.id) THEN 1 ELSE 0 END as has_org_type
            FROM organizations o
            WHERE o.status = 'approved' AND o.deleted_at IS NULL
            GROUP BY has_thematic, has_specialist, has_service, has_ownership, has_org_type
            ORDER BY cnt DESC
        ");

        $this->info('=== Статистика привязок организаций к справочникам ===');
        $this->newLine();

        $this->table(
            ['Справочник', 'С привязкой', 'Без привязки', 'Процент заполненности'],
            [
                ['Thematic Category', $withThematic, $withoutThematic, round($withThematic / $total * 100, 1).'%'],
                ['Specialist Profile', $withSpecialistProfile, $total - $withSpecialistProfile, round($withSpecialistProfile / $total * 100, 1).'%'],
                ['Service', $withService, $total - $withService, round($withService / $total * 100, 1).'%'],
                ['Ownership Type', $withOwnershipType, $total - $withOwnershipType, round($withOwnershipType / $total * 100, 1).'%'],
                ['Organization Type', $withOrganizationType, $total - $withOrganizationType, round($withOrganizationType / $total * 100, 1).'%'],
            ]
        );

        $this->newLine();
        $this->warn("⚠️  ПРОБЛЕМНАЯ ЗОНА: {$withoutThematic} организаций ({$this->percentage($withoutThematic, $total)}) БЕЗ привязки к Thematic Category");
        $this->newLine();

        $this->info('=== Распределение по комбинациям привязок ===');
        $this->table(
            ['Thematic', 'Specialist', 'Service', 'Ownership', 'Org Type', 'Количество', '%'],
            array_map(function ($s) use ($total) {
                return [
                    $s->has_thematic ? '✓' : '✗',
                    $s->has_specialist ? '✓' : '✗',
                    $s->has_service ? '✓' : '✗',
                    $s->has_ownership ? '✓' : '✗',
                    $s->has_org_type ? '✓' : '✗',
                    $s->cnt,
                    $this->percentage($s->cnt, $total),
                ];
            }, array_slice($stats, 0, 15))
        );

        if (count($stats) > 15) {
            $this->line('... и еще '.(count($stats) - 15).' комбинаций');
        }

        // Show examples of organizations without thematic category
        $this->newLine();
        $this->info('=== Примеры организаций БЕЗ Thematic Category (первые 10) ===');
        $examples = DB::select("
            SELECT o.id, o.title, o.inn, o.ogrn
            FROM organizations o
            WHERE o.status = 'approved' 
              AND o.deleted_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM organization_thematic_categories 
                WHERE organization_id = o.id
              )
            LIMIT 10
        ");

        $this->table(
            ['ID', 'Название', 'ИНН', 'ОГРН'],
            array_map(function ($e) {
                return [
                    substr($e->id, 0, 8).'...',
                    mb_substr($e->title, 0, 40),
                    $e->inn ?? '-',
                    $e->ogrn ?? '-',
                ];
            }, $examples)
        );

        return self::SUCCESS;
    }

    private function percentage(int $part, int $total): string
    {
        return round($part / $total * 100, 1).'%';
    }
}
