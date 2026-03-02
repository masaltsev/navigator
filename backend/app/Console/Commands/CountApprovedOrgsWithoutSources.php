<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Models\Organizer;
use App\Models\Source;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Count approved organizations that have no active sources (any kind).
 * Optionally: from reject.json (minus review.json) — e.g. data/runs/2026-02-25_no_sources/reject.json
 * — count how many of those orgs are still without sources.
 * JSON may have org_id (run output) or only source_id (tiered_test); both are supported.
 */
class CountApprovedOrgsWithoutSources extends Command
{
    protected $signature = 'orgs:count-approved-without-sources
                            {--reject= : Path to tiered_test_reject.json (harvester data)}
                            {--review= : Path to tiered_test_review.json (harvester data)}
                            {--list : List org IDs from reject\\review subset that are still without sources}';

    protected $description = 'Count approved orgs with no active sources; optionally filter by reject/review JSON';

    public function handle(): int
    {
        // 1) Total approved orgs without any active source
        $totalWithoutSources = Organization::query()
            ->whereNull('organizations.deleted_at')
            ->where('organizations.status', 'approved')
            ->whereNotExists(function ($sub) {
                $sub->select(DB::raw(1))
                    ->from('organizers')
                    ->join('sources', 'sources.organizer_id', '=', 'organizers.id')
                    ->whereColumn('organizers.organizable_id', 'organizations.id')
                    ->where('organizers.organizable_type', 'like', '%Organization%')
                    ->whereNull('sources.deleted_at')
                    ->where('sources.is_active', true);
            })
            ->join('organizers', function ($join) {
                $join->on('organizers.organizable_id', '=', 'organizations.id')
                    ->where('organizers.organizable_type', 'like', '%Organization%');
            })
            ->count();

        $this->info('Approved organizations without any active source (total): '.$totalWithoutSources);

        $rejectPath = $this->option('reject');
        $reviewPath = $this->option('review');

        if ($rejectPath === null || $reviewPath === null) {
            $this->newLine();
            $this->comment('To check subset from reject (excluding review):');
            $this->comment('  php artisan orgs:count-approved-without-sources --reject=../ai-pipeline/harvester/data/runs/2026-02-25_no_sources/reject.json --review=../ai-pipeline/harvester/data/runs/2026-02-25_no_sources/review.json');

            return self::SUCCESS;
        }

        $rejectData = $this->loadJson($rejectPath);
        $reviewData = $this->loadJson($reviewPath);
        if ($rejectData === null || $reviewData === null) {
            return self::FAILURE;
        }

        $rejectOrgIds = $this->extractOrgIds($rejectData, 'reject', $rejectPath);
        $reviewOrgIds = $this->extractOrgIds($reviewData, 'review', $reviewPath);
        if ($rejectOrgIds === null || $reviewOrgIds === null) {
            return self::FAILURE;
        }

        $rejectOnlyOrgIds = array_values(array_diff($rejectOrgIds, $reviewOrgIds));

        $this->newLine();
        $this->info('From reject file: '.count($rejectOrgIds).' org(s)');
        $this->info('From review file: '.count($reviewOrgIds).' org(s)');
        $this->info('Reject \\ Review (orgs only in reject): '.count($rejectOnlyOrgIds).' org(s)');

        if (count($rejectOnlyOrgIds) === 0) {
            return self::SUCCESS;
        }

        $stillWithoutSources = Organization::query()
            ->whereIn('organizations.id', $rejectOnlyOrgIds)
            ->where('organizations.status', 'approved')
            ->whereNull('organizations.deleted_at')
            ->whereNotExists(function ($sub) {
                $sub->select(DB::raw(1))
                    ->from('organizers')
                    ->join('sources', 'sources.organizer_id', '=', 'organizers.id')
                    ->whereColumn('organizers.organizable_id', 'organizations.id')
                    ->where('organizers.organizable_type', 'like', '%Organization%')
                    ->whereNull('sources.deleted_at')
                    ->where('sources.is_active', true);
            })
            ->get();

        $count = $stillWithoutSources->count();
        $this->info('Of those (reject \\ review), still without any active source: '.$count);

        if ($this->option('list') && $stillWithoutSources->isNotEmpty()) {
            $this->newLine();
            $this->table(
                ['org_id', 'title'],
                $stillWithoutSources->map(fn ($o) => [$o->id, mb_substr($o->title ?? '', 0, 60)])->all()
            );
        }

        return self::SUCCESS;
    }

    /**
     * Extract org IDs from JSON rows. Prefers org_id if present (run output); else resolves source_id via DB.
     *
     * @param  array<int, mixed>  $data
     * @return array<string>|null
     */
    private function extractOrgIds(array $data, string $label, string $path): ?array
    {
        if (empty($data)) {
            return [];
        }

        $first = $data[0];
        if (is_array($first) && array_key_exists('org_id', $first)) {
            $ids = array_filter(array_column($data, 'org_id'));

            return array_values(array_unique($ids));
        }

        $sourceIds = array_column($data, 'source_id');

        return $this->sourceIdsToOrgIds($sourceIds);
    }

    /**
     * @param  array<string>  $sourceIds
     * @return array<string>
     */
    private function sourceIdsToOrgIds(array $sourceIds): array
    {
        if (empty($sourceIds)) {
            return [];
        }

        $organizerIds = Source::query()
            ->whereIn('id', $sourceIds)
            ->whereNull('deleted_at')
            ->whereNotNull('organizer_id')
            ->pluck('organizer_id')
            ->unique()
            ->all();

        if (empty($organizerIds)) {
            return [];
        }

        return Organizer::query()
            ->whereIn('id', $organizerIds)
            ->where('organizable_type', 'like', '%Organization%')
            ->pluck('organizable_id')
            ->unique()
            ->values()
            ->all();
    }

    /** @return array<int, mixed>|null */
    private function loadJson(string $path): ?array
    {
        $fullPath = realpath($path);
        if ($fullPath === false || ! is_file($fullPath)) {
            $this->error('File not found: '.$path);

            return null;
        }

        $json = file_get_contents($fullPath);
        $data = json_decode($json, true);
        if (! is_array($data)) {
            $this->error('Invalid JSON or not array: '.$path);

            return null;
        }

        return $data;
    }
}
