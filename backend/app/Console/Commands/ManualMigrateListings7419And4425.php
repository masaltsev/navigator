<?php

namespace App\Console\Commands;

use App\Models\Organization;
use App\Services\WpMigration\WpListingRepository;
use App\Services\WpMigration\WpTaxonomyMapper;
use App\Services\WpMigration\WpToCoreMigrator;
use Illuminate\Console\Command;

/**
 * Temporary command: manually migrate listing 7419 (with short title) and update org from 4425 (replacing 3799 data).
 *
 * Remove after use or keep for reference.
 */
class ManualMigrateListings7419And4425 extends Command
{
    protected $signature = 'navigator:manual-migrate-7419-4425';

    protected $description = 'Temporary: migrate listing 7419 with short title; update existing org (3799) with listing 4425 data';

    public function handle(): int
    {
        $repo = new WpListingRepository;
        $taxonomyMapper = new WpTaxonomyMapper;
        $migrator = new WpToCoreMigrator($taxonomyMapper);
        $migrator->initialize();

        // 1) Listing 7419 — migrate with shortened title (fits varchar 255)
        $this->info('Processing listing 7419 (title override)...');
        $listings7419 = $repo->getListingsByPostIds([7419]);
        if (empty($listings7419)) {
            $this->error('Listing 7419 not found in WP.');

            return Command::FAILURE;
        }
        $listing7419 = $listings7419[0];
        $taxonomies7419 = $repo->getAllTaxonomiesForListing(7419);
        $title7419 = 'ПРАВОСЛАВНЫЙ ПРИХОД ХРАМА СВЯТИТЕЛЯ НИКОЛАЯ, АРХИЕПИСКОПА МИР ЛИКИЙСКИХ ЧУДОТВОРЦА';
        $result = $migrator->migrateListingWithOverrides($listing7419, $taxonomies7419, ['title' => $title7419]);
        $this->info("  7419 → organization id: {$result['organization']->id}, created: ".($result['created'] ? 'yes' : 'no'));

        // 2) Listing 4425 — update existing organization (created from 3799) with 4425 data
        $this->info('Processing listing 4425 (update org that was created from 3799)...');
        $org = Organization::where('ogrn', '1027301489456')->first();
        if (! $org) {
            $this->error('Organization with OGRN 1027301489456 not found in Core.');

            return Command::FAILURE;
        }
        $listings4425 = $repo->getListingsByPostIds([4425]);
        if (empty($listings4425)) {
            $this->error('Listing 4425 not found in WP.');

            return Command::FAILURE;
        }
        $listing4425 = $listings4425[0];
        $taxonomies4425 = $repo->getAllTaxonomiesForListing(4425);
        $migrator->updateOrganizationFromListing($org, $listing4425, $taxonomies4425);
        $this->info("  4425 → updated organization id: {$org->id} (title, site_urls, contacts, venue, sources).");

        $this->newLine();
        $this->info('Done.');

        return Command::SUCCESS;
    }
}
