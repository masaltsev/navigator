<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Models\Organizer;
use App\Models\Source;
use Illuminate\Console\Command;
use Illuminate\Support\Str;

/**
 * Create org_website sources from organization.site_urls and link them to organizers.
 * For each URL in site_urls, creates a source if it doesn't exist yet.
 */
class CreateOrgWebsiteSourcesFromSiteUrls extends Command
{
    protected $signature = 'sources:create-from-site-urls
                            {--dry-run : Do not save, only show planned creations}
                            {--limit=0 : Max organizations to process (0 = no limit)}';

    protected $description = 'Create org_website sources from organization.site_urls and link to organizers';

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $limit = (int) $this->option('limit');

        $query = Organization::query()
            ->where('status', 'approved')
            ->whereNotNull('site_urls')
            ->whereHas('organizer')
            ->with('organizer');

        if ($limit > 0) {
            $query->limit($limit);
        }

        $organizations = $query->get();
        if ($organizations->isEmpty()) {
            $this->info('No organizations with site_urls and organizer to process.');

            return self::SUCCESS;
        }

        $this->info('Processing '.$organizations->count().' organization(s). dry-run='.($dryRun ? 'yes' : 'no'));

        $created = 0;
        $skipped = 0;
        $errors = 0;

        foreach ($organizations as $organization) {
            $siteUrls = $organization->site_urls ?? [];
            if (! is_array($siteUrls) || empty($siteUrls)) {
                continue;
            }

            $organizer = $organization->organizer;
            if (! $organizer) {
                $this->warn("  [{$organization->id}] No organizer found, skipping");
                $skipped++;

                continue;
            }

            foreach ($siteUrls as $siteUrl) {
                if (! is_string($siteUrl) || $siteUrl === '') {
                    continue;
                }

                $normalizedUrl = $this->normalizeUrl($siteUrl);
                if ($normalizedUrl === null) {
                    continue;
                }

                // Check if source with this base_url already exists (exact match or normalized match)
                $existingSource = Source::where('kind', 'org_website')
                    ->where(function ($q) use ($siteUrl, $normalizedUrl) {
                        $q->where('base_url', $siteUrl)
                            ->orWhere(function ($q2) use ($normalizedUrl) {
                                // Try to match normalized URLs
                                $q2->whereRaw("LOWER(REGEXP_REPLACE(REGEXP_REPLACE(base_url, '^https?://', ''), '^www\\.', '')) = ?", [$normalizedUrl]);
                            });
                    })
                    ->first();

                if ($existingSource) {
                    // If exists but not linked to our organizer, link it
                    if ($existingSource->organizer_id !== $organizer->id) {
                        if (! $dryRun) {
                            $existingSource->organizer_id = $organizer->id;
                            $existingSource->save();
                        }
                        if ($this->output->isVerbose()) {
                            $this->line("  [{$organization->id}] Linked existing source {$existingSource->id} to organizer");
                        }
                    } else {
                        if ($this->output->isVerbose()) {
                            $this->line("  [{$organization->id}] Source already exists and linked: {$siteUrl}");
                        }
                    }

                    continue;
                }

                // Create new source
                if (! $dryRun) {
                    try {
                        // Extract hostname safely (handles Cyrillic domains)
                        $parsed = @parse_url($siteUrl);
                        $hostname = $parsed['host'] ?? null;

                        // If parse_url fails (e.g., Cyrillic domains), extract manually
                        if (! $hostname || ! mb_check_encoding($hostname, 'UTF-8')) {
                            $hostname = preg_replace('#^https?://#i', '', $siteUrl);
                            $hostname = preg_replace('#^www\.#i', '', $hostname);
                            $hostname = preg_replace('#/.*$#', '', $hostname);
                            $hostname = preg_replace('#\?.*$#', '', $hostname);
                        }

                        // Validate encoding and use URL itself if extraction failed
                        if (empty($hostname) || ! mb_check_encoding($hostname, 'UTF-8') || mb_strlen($hostname) > 255) {
                            $hostname = mb_substr($siteUrl, 0, 255);
                        }

                        $source = Source::create([
                            'id' => (string) Str::uuid(),
                            'name' => mb_substr($hostname, 0, 255),
                            'kind' => 'org_website',
                            'base_url' => $siteUrl,
                            'entry_points' => [],
                            'is_active' => true,
                            'last_status' => 'pending',
                            'organizer_id' => $organizer->id,
                        ]);
                        $created++;
                        if ($this->output->isVerbose()) {
                            $this->info("  [{$organization->id}] Created source {$source->id} for: {$siteUrl}");
                        }
                    } catch (\Exception $e) {
                        $errors++;
                        $this->error("  [{$organization->id}] Failed to create source for {$siteUrl}: {$e->getMessage()}");
                    }
                } else {
                    $created++;
                    if ($this->output->isVerbose()) {
                        $this->line("  [{$organization->id}] Would create source for: {$siteUrl}");
                    }
                }
            }
        }

        $this->newLine();
        $this->info("Done. Created: {$created}, skipped: {$skipped}, errors: {$errors}.");

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
}
