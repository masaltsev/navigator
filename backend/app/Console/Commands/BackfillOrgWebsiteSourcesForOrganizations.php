<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Models\Organizer;
use App\Models\Source;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

/**
 * Backfill org_website sources for organizations that have site_urls but no org_website source.
 * - Creates organizer if missing.
 * - Skips if organizer has any source (other than org_website) with base_url (to process separately).
 * - Otherwise creates org_website source(s) from site_urls and links via organizer_id.
 */
class BackfillOrgWebsiteSourcesForOrganizations extends Command
{
    protected $signature = 'sources:backfill-org-websites
                            {--dry-run : Do not save, only show planned actions}
                            {--limit=0 : Max organizations to process (0 = no limit)}';

    protected $description = 'Backfill org_website sources for organizations with site_urls but no org_website source';

    public function handle(): int
    {
        $dryRun = (bool) $this->option('dry-run');
        $limit = (int) $this->option('limit');

        // Organizations with site_urls that do NOT have org_website source (via organizer)
        $orgIds = DB::select("
            SELECT o.id
            FROM organizations o
            WHERE o.status = 'approved'
              AND o.deleted_at IS NULL
              AND o.site_urls IS NOT NULL
              AND o.site_urls::text != '[]'::text
              AND NOT EXISTS (
                SELECT 1 FROM organizers org
                JOIN sources s ON s.organizer_id = org.id AND s.kind = 'org_website'
                WHERE org.organizable_type = 'Organization' AND org.organizable_id = o.id
              )
            ORDER BY o.id
        ");

        $orgIds = array_column($orgIds, 'id');
        if ($limit > 0) {
            $orgIds = array_slice($orgIds, 0, $limit);
        }

        if (empty($orgIds)) {
            $this->info('No organizations with site_urls missing org_website source.');

            return self::SUCCESS;
        }

        $this->info('Processing '.count($orgIds).' organization(s). dry-run='.($dryRun ? 'yes' : 'no'));

        $organizersCreated = 0;
        $sourcesCreated = 0;
        $skippedHasOtherSource = 0;
        $errors = 0;

        foreach ($orgIds as $orgId) {
            $organization = Organization::with('organizer.sources')->find($orgId);
            if (! $organization) {
                continue;
            }

            $siteUrls = $organization->site_urls ?? [];
            if (! is_array($siteUrls) || empty($siteUrls)) {
                continue;
            }

            // Get or create organizer
            $organizer = $organization->organizer;
            if (! $organizer) {
                if (! $dryRun) {
                    $organizer = Organizer::create([
                        'organizable_type' => 'Organization',
                        'organizable_id' => $organization->id,
                        'contact_phones' => null,
                        'contact_emails' => null,
                        'status' => 'approved',
                    ]);
                    $organizersCreated++;
                } else {
                    $organizer = new Organizer(['id' => Str::uuid()]);
                }
                if ($this->output->isVerbose()) {
                    $this->line("  [{$organization->id}] Created organizer");
                }
            }

            // Skip if organizer has any source (other kind) with base_url filled
            $hasOtherSourceWithUrl = $organizer->sources
                ->filter(fn ($s) => $s->kind !== 'org_website' && ! empty(trim((string) $s->base_url)))
                ->isNotEmpty();

            if ($hasOtherSourceWithUrl) {
                $skippedHasOtherSource++;
                if ($this->output->isVerbose()) {
                    $this->line("  [{$organization->id}] Skipped: has source with other type and base_url");
                }

                continue;
            }

            foreach ($siteUrls as $siteUrl) {
                if (! is_string($siteUrl) || trim($siteUrl) === '') {
                    continue;
                }

                $siteUrl = trim($siteUrl);
                $normalizedUrl = $this->normalizeUrl($siteUrl);
                if ($normalizedUrl === null) {
                    continue;
                }

                // Check if this organizer already has an org_website source for this URL
                $existingForOrganizer = Source::where('kind', 'org_website')
                    ->where('organizer_id', $organizer->id)
                    ->where(function ($q) use ($siteUrl, $normalizedUrl) {
                        $q->where('base_url', $siteUrl)
                            ->orWhereRaw("LOWER(REGEXP_REPLACE(REGEXP_REPLACE(base_url, '^https?://', ''), '^www\\.', '')) = ?", [$normalizedUrl]);
                    })
                    ->first();

                if ($existingForOrganizer) {
                    continue;
                }

                // If source exists with same URL but another organizer_id, link it only when unlinked (organizer_id null)
                $existingUnlinked = Source::where('kind', 'org_website')
                    ->whereNull('organizer_id')
                    ->where(function ($q) use ($siteUrl, $normalizedUrl) {
                        $q->where('base_url', $siteUrl)
                            ->orWhereRaw("LOWER(REGEXP_REPLACE(REGEXP_REPLACE(base_url, '^https?://', ''), '^www\\.', '')) = ?", [$normalizedUrl]);
                    })
                    ->first();

                if ($existingUnlinked && ! $dryRun) {
                    $existingUnlinked->organizer_id = $organizer->id;
                    $existingUnlinked->save();
                    $sourcesCreated++;

                    continue;
                }

                if (! $dryRun) {
                    try {
                        $hostname = $this->extractHostname($siteUrl);
                        Source::create([
                            'id' => (string) Str::uuid(),
                            'name' => mb_substr($hostname, 0, 255),
                            'kind' => 'org_website',
                            'base_url' => $siteUrl,
                            'entry_points' => [],
                            'is_active' => true,
                            'last_status' => 'pending',
                            'organizer_id' => $organizer->id,
                        ]);
                        $sourcesCreated++;
                        if ($this->output->isVerbose()) {
                            $this->info("  [{$organization->id}] Created source for: {$siteUrl}");
                        }
                    } catch (\Exception $e) {
                        $errors++;
                        $this->error("  [{$organization->id}] Failed: {$siteUrl} — {$e->getMessage()}");
                    }
                } else {
                    $sourcesCreated++;
                }
            }
        }

        $this->newLine();
        $this->info("Done. Organizers created: {$organizersCreated}, sources created: {$sourcesCreated}, skipped (has other source): {$skippedHasOtherSource}, errors: {$errors}.");

        return self::SUCCESS;
    }

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

    private function extractHostname(string $siteUrl): string
    {
        $parsed = @parse_url($siteUrl);
        $hostname = $parsed['host'] ?? null;

        if (! $hostname || ! mb_check_encoding($hostname, 'UTF-8')) {
            $hostname = preg_replace('#^https?://#i', '', $siteUrl);
            $hostname = preg_replace('#^www\.#i', '', $hostname);
            $hostname = preg_replace('#/.*$#', '', $hostname);
            $hostname = preg_replace('#\?.*$#', '', $hostname);
        }

        if (empty($hostname) || ! mb_check_encoding($hostname, 'UTF-8') || mb_strlen($hostname) > 255) {
            $hostname = mb_substr($siteUrl, 0, 255);
        }

        return $hostname;
    }
}
