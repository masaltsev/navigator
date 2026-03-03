<?php

namespace App\Console\Commands;

use App\Models\Organization;
use Illuminate\Console\Command;

/**
 * Verify that organization.site_urls match org_website sources linked via organizer.
 * Checks for consistency and reports mismatches.
 */
class VerifyOrgWebsiteSourcesConsistency extends Command
{
    protected $signature = 'sources:verify-consistency
                            {--limit=0 : Max organizations to check (0 = no limit)}
                            {--show-mismatches : Show detailed mismatch examples}';

    protected $description = 'Verify consistency between organization.site_urls and org_website sources';

    public function handle(): int
    {
        $limit = (int) $this->option('limit');
        $showMismatches = (bool) $this->option('show-mismatches');

        $query = Organization::query()
            ->where('status', 'approved')
            ->whereNotNull('site_urls')
            ->whereRaw("site_urls::text != '[]'::text")
            ->with(['organizer.sources' => function ($q) {
                $q->where('kind', 'org_website');
            }]);

        if ($limit > 0) {
            $query->limit($limit);
        }

        $organizations = $query->get();
        $this->info('Checking '.$organizations->count().' organization(s)...');

        $perfect = 0;
        $missingSources = 0;
        $extraSources = 0;
        $partialMatches = 0;
        $mismatches = [];

        foreach ($organizations as $org) {
            $siteUrls = $org->site_urls ?? [];
            if (! is_array($siteUrls) || empty($siteUrls)) {
                continue;
            }

            $organizer = $org->organizer;
            if (! $organizer) {
                $missingSources++;
                $mismatches[] = [
                    'org_id' => $org->id,
                    'org_title' => $org->title,
                    'issue' => 'no_organizer',
                    'site_urls' => $siteUrls,
                    'sources' => [],
                ];

                continue;
            }

            $sources = $organizer->sources;
            $normalizedSiteUrls = array_filter(array_map([$this, 'normalizeUrl'], $siteUrls));
            $normalizedSourceUrls = $sources->map(fn ($s) => $this->normalizeUrl($s->base_url))->filter()->toArray();

            // Check each site_url has matching source
            $unmatchedSiteUrls = [];
            foreach ($normalizedSiteUrls as $normalizedSiteUrl) {
                $found = false;
                foreach ($normalizedSourceUrls as $normalizedSourceUrl) {
                    if ($this->urlsMatch($normalizedSiteUrl, $normalizedSourceUrl)) {
                        $found = true;

                        break;
                    }
                }
                if (! $found) {
                    $unmatchedSiteUrls[] = $normalizedSiteUrl;
                }
            }

            // Check each source has matching site_url
            $unmatchedSources = [];
            foreach ($normalizedSourceUrls as $normalizedSourceUrl) {
                $found = false;
                foreach ($normalizedSiteUrls as $normalizedSiteUrl) {
                    if ($this->urlsMatch($normalizedSiteUrl, $normalizedSourceUrl)) {
                        $found = true;

                        break;
                    }
                }
                if (! $found) {
                    $unmatchedSources[] = $normalizedSourceUrl;
                }
            }

            if (empty($unmatchedSiteUrls) && empty($unmatchedSources)) {
                $perfect++;
            } else {
                if (! empty($unmatchedSiteUrls)) {
                    $missingSources++;
                }
                if (! empty($unmatchedSources)) {
                    $extraSources++;
                }
                if (! empty($unmatchedSiteUrls) && ! empty($unmatchedSources)) {
                    $partialMatches++;
                }

                if ($showMismatches && count($mismatches) < 20) {
                    $mismatches[] = [
                        'org_id' => $org->id,
                        'org_title' => substr($org->title, 0, 50),
                        'site_urls' => $siteUrls,
                        'source_urls' => $sources->pluck('base_url')->toArray(),
                        'unmatched_site_urls' => $unmatchedSiteUrls,
                        'unmatched_source_urls' => $unmatchedSources,
                    ];
                }
            }
        }

        $this->newLine();
        $this->info('=== Результаты проверки ===');
        $this->table(
            ['Метрика', 'Количество'],
            [
                ['Всего проверено организаций', $organizations->count()],
                ['Идеальное совпадение (все URL совпадают)', $perfect],
                ['Есть URL в site_urls без источника', $missingSources],
                ['Есть источники без URL в site_urls', $extraSources],
                ['Частичные несоответствия', $partialMatches],
            ]
        );

        if ($showMismatches && ! empty($mismatches)) {
            $this->newLine();
            $this->warn('Примеры несоответствий (первые '.min(20, count($mismatches)).'):');
            foreach ($mismatches as $mismatch) {
                $this->line("  Организация: {$mismatch['org_title']} ({$mismatch['org_id']})");
                if (isset($mismatch['issue']) && $mismatch['issue'] === 'no_organizer') {
                    $this->line('    ❌ Нет организатора');
                } else {
                    if (! empty($mismatch['unmatched_site_urls'])) {
                        $this->line('    ⚠️  URL в site_urls без источника: '.implode(', ', array_slice($mismatch['unmatched_site_urls'], 0, 3)));
                    }
                    if (! empty($mismatch['unmatched_source_urls'])) {
                        $this->line('    ⚠️  Источники без URL в site_urls: '.implode(', ', array_slice($mismatch['unmatched_source_urls'], 0, 3)));
                    }
                }
            }
        }

        return self::SUCCESS;
    }

    /**
     * Normalize URL for comparison: remove protocol, www, trailing slash, convert to lowercase.
     */
    private function normalizeUrl(?string $url): ?string
    {
        if ($url === null || $url === '') {
            return null;
        }

        $url = trim($url);
        $url = preg_replace('#^https?://#i', '', $url);
        $url = preg_replace('#^www\.#i', '', $url);
        $url = rtrim($url, '/');
        $url = mb_strtolower($url);

        return $url !== '' ? $url : null;
    }

    /**
     * Check if two normalized URLs match (exact or substring match).
     */
    private function urlsMatch(string $url1, string $url2): bool
    {
        if ($url1 === $url2) {
            return true;
        }

        // Substring match: one URL contains the other (for cases like "example.com" vs "www.example.com/path")
        return str_contains($url1, $url2) || str_contains($url2, $url1);
    }
}
