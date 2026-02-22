<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Models\Organizer;
use App\Models\Source;
use Illuminate\Console\Command;

/**
 * Link org_website sources to organizers by matching base_url with organization site_urls.
 */
class LinkOrgWebsiteSourcesToOrganizers extends Command
{
    protected $signature = 'sources:link-org-websites
                            {--dry-run : Do not save, only show planned links}
                            {--limit=0 : Max sources to process (0 = no limit)}';

    protected $description = 'Link org_website sources to organizers by matching base_url with organization site_urls';

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $limit = (int) $this->option('limit');

        $query = Source::query()
            ->where('kind', 'org_website')
            ->whereNull('organizer_id')
            ->whereNotNull('base_url')
            ->where('base_url', '!=', '');

        if ($limit > 0) {
            $query->limit($limit);
        }

        $sources = $query->get();
        if ($sources->isEmpty()) {
            $this->info('No org_website sources without organizer_id to process.');

            return self::SUCCESS;
        }

        $this->info('Processing '.$sources->count().' source(s). dry-run='.($dryRun ? 'yes' : 'no'));

        $linked = 0;
        $notFound = 0;

        foreach ($sources as $source) {
            $normalizedSourceUrl = $this->normalizeUrl($source->base_url);
            if ($normalizedSourceUrl === null) {
                continue;
            }

            // Find organization with matching URL in site_urls
            $organization = $this->findOrganizationByUrl($normalizedSourceUrl);
            if (! $organization) {
                $notFound++;
                if ($this->output->isVerbose()) {
                    $this->line("  [{$source->id}] No match for: {$source->base_url}");
                }

                continue;
            }

            // Get or create organizer
            // Use firstOrCreate to avoid duplicates if relation doesn't work
            $organizer = $organization->organizer;
            if (! $organizer) {
                if (! $dryRun) {
                    // Double-check with direct query to avoid duplicates
                    $existing = Organizer::where('organizable_type', 'Organization')
                        ->where('organizable_id', $organization->id)
                        ->first();

                    if ($existing) {
                        $organizer = $existing;
                    } else {
                        $organizer = Organizer::create([
                            'organizable_type' => 'Organization',
                            'organizable_id' => $organization->id,
                            'contact_phones' => null,
                            'contact_emails' => null,
                            'status' => 'approved',
                        ]);
                    }
                } else {
                    $this->line("  [{$source->id}] Would create organizer for: {$organization->title}");
                }
            }

            if (! $dryRun && $organizer) {
                $source->organizer_id = $organizer->id;
                $source->save();
            }

            $linked++;
            if ($this->output->isVerbose()) {
                $this->info("  [{$source->id}] Linked to: {$organization->title} ({$organization->id})");
            }
        }

        $this->newLine();
        $this->info("Done. Linked: {$linked}, not found: {$notFound}.");

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
     * Find organization where site_urls contains a URL matching the normalized source URL.
     */
    private function findOrganizationByUrl(string $normalizedSourceUrl): ?Organization
    {
        // Get all organizations with site_urls
        $organizations = Organization::query()
            ->where('status', 'approved')
            ->whereNotNull('site_urls')
            ->get();

        foreach ($organizations as $org) {
            $siteUrls = $org->site_urls ?? [];
            if (! is_array($siteUrls)) {
                continue;
            }

            foreach ($siteUrls as $siteUrl) {
                if (! is_string($siteUrl) || $siteUrl === '') {
                    continue;
                }

                $normalizedOrgUrl = $this->normalizeUrl($siteUrl);
                if ($normalizedOrgUrl === null) {
                    continue;
                }

                // Match: exact match or source URL is substring of org URL (or vice versa)
                if ($normalizedSourceUrl === $normalizedOrgUrl
                    || str_contains($normalizedSourceUrl, $normalizedOrgUrl)
                    || str_contains($normalizedOrgUrl, $normalizedSourceUrl)) {
                    return $org;
                }
            }
        }

        return null;
    }
}
