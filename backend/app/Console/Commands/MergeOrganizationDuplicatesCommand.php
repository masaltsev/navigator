<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Models\Organizer;
use App\Services\Import\OrganizationDuplicateMergeService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

class MergeOrganizationDuplicatesCommand extends Command
{
    protected $signature = 'db:merge-org-duplicates
                            {--dry-run : Show planned merges without changing data}
                            {--force : Perform merges (required with non-dry-run)}
                            {--report : Print organizations whose source_reference does not match any linked source base_url}';

    protected $description = 'Merge crawler duplicate organizations into canonical INN/OGRN records; clean unknown placeholders';

    public function handle(OrganizationDuplicateMergeService $mergeService): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $force = (bool) $this->option('force');

        if ($this->option('report')) {
            $this->reportSourceReferenceMismatches();

            return self::SUCCESS;
        }

        if (! $dryRun && ! $force) {
            $this->error('Use --dry-run to preview or --force to execute.');

            return self::FAILURE;
        }

        $pairs = $this->fetchSourceLinkedDuplicatePairs();
        $this->info('Source-linked duplicates (newer org with empty INN/OGRN → canonical with legal ids): '.$pairs->count());

        foreach ($pairs as $row) {
            $this->line("  duplicate {$row->duplicate_id} → canonical {$row->canonical_id}");
            if ($dryRun) {
                continue;
            }
            $canon = Organization::query()->whereKey($row->canonical_id)->first();
            $dup = Organization::query()->whereKey($row->duplicate_id)->first();
            if ($canon && $dup) {
                $mergeService->mergeDuplicateIntoCanonical($canon, $dup);
            }
        }

        $unknownMerged = $this->fetchUnknownOrganizationPairs();
        $this->info('Unknown-title rows with resolvable canonical via source URL: '.$unknownMerged->count());
        foreach ($unknownMerged as $row) {
            $this->line("  unknown {$row->duplicate_id} → canonical {$row->canonical_id}");
            if ($dryRun) {
                continue;
            }
            $canon = Organization::query()->whereKey($row->canonical_id)->first();
            $dup = Organization::query()->whereKey($row->duplicate_id)->first();
            if ($canon && $dup) {
                $mergeService->mergeDuplicateIntoCanonical($canon, $dup);
            }
        }

        $skipOrphan = $pairs->pluck('duplicate_id')
            ->merge($unknownMerged->pluck('duplicate_id'))
            ->unique()
            ->flip();

        $orphanUnknowns = $this->fetchOrphanUnknownOrganizations()->reject(
            fn (string $id): bool => $skipOrphan->has($id)
        )->values();
        $this->info('Orphan unknown-title orgs (no events/articles, will soft-delete): '.$orphanUnknowns->count());
        foreach ($orphanUnknowns as $id) {
            $this->line("  delete orphan {$id}");
            if ($dryRun) {
                continue;
            }
            $org = Organization::query()->whereKey($id)->first();
            if ($org) {
                $organizer = Organizer::query()
                    ->where('organizable_type', 'Organization')
                    ->where('organizable_id', $org->id)
                    ->whereNull('deleted_at')
                    ->first();
                $org->delete();
                $organizer?->delete();
            }
        }

        if ($dryRun) {
            $this->warn('Dry run — no changes.');
        } else {
            $this->info('Done.');
        }

        return self::SUCCESS;
    }

    /**
     * @return \Illuminate\Support\Collection<int, object{duplicate_id: string, canonical_id: string}>
     */
    private function fetchSourceLinkedDuplicatePairs(): \Illuminate\Support\Collection
    {
        $rows = DB::select('
            SELECT DISTINCT ON (dup.id)
                dup.id::text AS duplicate_id,
                canon.id::text AS canonical_id
            FROM organizations dup
            INNER JOIN sources s
                ON s.deleted_at IS NULL
                AND s.organizer_id IS NOT NULL
                AND (
                    s.base_url = dup.source_reference
                    OR s.base_url = rtrim(dup.source_reference, \'/\')
                    OR s.base_url = regexp_replace(dup.source_reference, \'^https?://m\\\\.ok\\\\.ru/\', \'https://ok.ru/\', \'i\')
                    OR s.base_url = regexp_replace(dup.source_reference, \'^https?://ok\\\\.ru/\', \'https://m.ok.ru/\', \'i\')
                )
            INNER JOIN organizers o ON o.id = s.organizer_id AND o.deleted_at IS NULL AND o.organizable_type = \'Organization\'
            INNER JOIN organizations canon ON canon.id = o.organizable_id AND canon.deleted_at IS NULL
            WHERE dup.deleted_at IS NULL
              AND dup.id <> canon.id
              AND dup.source_reference IS NOT NULL AND btrim(dup.source_reference) <> \'\'
              AND (NULLIF(btrim(dup.inn), \'\') IS NULL AND NULLIF(btrim(dup.ogrn), \'\') IS NULL)
              AND (NULLIF(btrim(canon.inn), \'\') IS NOT NULL OR NULLIF(btrim(canon.ogrn), \'\') IS NOT NULL)
              AND dup.created_at > canon.created_at
            ORDER BY dup.id, canon.created_at ASC
        ');

        return collect($rows);
    }

    /**
     * @return \Illuminate\Support\Collection<int, object{duplicate_id: string, canonical_id: string}>
     */
    private function fetchUnknownOrganizationPairs(): \Illuminate\Support\Collection
    {
        $rows = DB::select('
            SELECT DISTINCT ON (dup.id)
                dup.id::text AS duplicate_id,
                canon.id::text AS canonical_id
            FROM organizations dup
            INNER JOIN sources s
                ON s.deleted_at IS NULL
                AND s.organizer_id IS NOT NULL
                AND (
                    s.base_url = dup.source_reference
                    OR s.base_url = rtrim(dup.source_reference, \'/\')
                    OR s.base_url = regexp_replace(dup.source_reference, \'^https?://m\\\\.ok\\\\.ru/\', \'https://ok.ru/\', \'i\')
                    OR s.base_url = regexp_replace(dup.source_reference, \'^https?://ok\\\\.ru/\', \'https://m.ok.ru/\', \'i\')
                )
            INNER JOIN organizers o ON o.id = s.organizer_id AND o.deleted_at IS NULL AND o.organizable_type = \'Organization\'
            INNER JOIN organizations canon ON canon.id = o.organizable_id AND canon.deleted_at IS NULL
            WHERE dup.deleted_at IS NULL
              AND dup.id <> canon.id
              AND dup.source_reference IS NOT NULL AND btrim(dup.source_reference) <> \'\'
              AND (NULLIF(btrim(canon.inn), \'\') IS NOT NULL OR NULLIF(btrim(canon.ogrn), \'\') IS NOT NULL)
              AND (
                dup.title ILIKE \'Неизвестная организация%\'
                OR dup.title ILIKE \'Не удалось определить%\'
                OR dup.title ILIKE \'Не определено%\'
              )
            ORDER BY dup.id, canon.created_at ASC
        ');

        return collect($rows);
    }

    /**
     * @return \Illuminate\Support\Collection<int, string>
     */
    private function fetchOrphanUnknownOrganizations(): \Illuminate\Support\Collection
    {
        return Organization::query()
            ->whereNull('deleted_at')
            ->where(function ($q): void {
                $q->whereRaw('title ILIKE ?', ['Неизвестная организация%'])
                    ->orWhereRaw('title ILIKE ?', ['Не удалось определить%'])
                    ->orWhereRaw('title ILIKE ?', ['Не определено%']);
            })
            ->whereDoesntHave('events')
            ->whereDoesntHave('articles')
            ->whereRaw(
                'NOT EXISTS (
                    SELECT 1 FROM organizers o
                    INNER JOIN sources s ON s.organizer_id = o.id AND s.deleted_at IS NULL
                    WHERE o.organizable_id = organizations.id
                      AND o.organizable_type = ?
                      AND o.deleted_at IS NULL
                )',
                ['Organization']
            )
            ->pluck('id');
    }

    private function reportSourceReferenceMismatches(): void
    {
        $rows = DB::select('
            SELECT o.id::text AS id, o.title, o.source_reference
            FROM organizations o
            INNER JOIN organizers org ON org.organizable_id = o.id
                AND org.organizable_type = \'Organization\'
                AND org.deleted_at IS NULL
            WHERE o.deleted_at IS NULL
              AND o.source_reference IS NOT NULL
              AND btrim(o.source_reference) <> \'\'
              AND NOT EXISTS (
                SELECT 1 FROM sources s
                WHERE s.organizer_id = org.id
                  AND s.deleted_at IS NULL
                  AND (
                    s.base_url = o.source_reference
                    OR s.base_url = rtrim(o.source_reference, \'/\')
                    OR s.base_url = regexp_replace(o.source_reference, \'^https?://m\\\\.ok\\\\.ru/\', \'https://ok.ru/\', \'i\')
                    OR s.base_url = regexp_replace(o.source_reference, \'^https?://ok\\\\.ru/\', \'https://m.ok.ru/\', \'i\')
                  )
              )
            ORDER BY o.updated_at DESC
            LIMIT 200
        ');

        $this->warn('Organizations with source_reference not matching any source on their organizer (max 200): '.count($rows));
        foreach ($rows as $r) {
            $this->line("  {$r->id} | {$r->title} | {$r->source_reference}");
        }
    }
}
