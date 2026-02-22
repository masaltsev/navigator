<?php

namespace App\Console\Commands;

use App\Services\WpMigration\WpListingRepository;
use App\Services\WpMigration\WpTaxonomyMapper;
use App\Services\WpMigration\WpToCoreMigrator;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Schema;

/**
 * Migrate data from WordPress/HivePress database to Navigator Core (Stage 0).
 *
 * This command performs the raw infrastructure migration:
 * - Extracts organizations, venues, and articles from WordPress
 * - Transforms EAV structure into relational Core schema
 * - Handles coordinate inversion, contact parsing, taxonomy mapping
 * - Ensures idempotency via updateOrCreate on INN/OGRN
 *
 * @see docs/wp_to_core_migration.md for detailed mapping rules
 * @see docs/wp_migration_design.md for architecture overview
 */
class MigrateFromWpBaseCommand extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'navigator:migrate-from-wp-base
                            {--chunk-size=500 : Number of records to process per batch}
                            {--skip-articles : Skip migrating WordPress posts as articles}
                            {--retry-failed : Re-process only failed listing IDs from storage/logs/wp-migration-failed-listings.txt}
                            {--retry-failed-file= : Custom path to file with failed listing IDs (one per line). Implies --retry-failed.}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Migrate organizations, venues, and articles from WordPress/HivePress to Navigator Core (Stage 0)';

    private WpListingRepository $wpRepository;

    private WpTaxonomyMapper $taxonomyMapper;

    private WpToCoreMigrator $migrator;

    private int $organizationsCreated = 0;

    private int $organizationsUpdated = 0;

    private int $venuesCreated = 0;

    private int $articlesCreated = 0;

    private int $errors = 0;

    private const FAILED_LISTINGS_FILE = 'wp-migration-failed-listings.txt';

    /**
     * Execute the console command.
     */
    public function handle(): int
    {
        $retryFile = $this->option('retry-failed-file') ?: ($this->option('retry-failed') ? storage_path('logs/'.self::FAILED_LISTINGS_FILE) : null);

        if ($retryFile !== null) {
            return $this->retryFailedListings($retryFile);
        }

        $this->info('Starting WordPress to Navigator Core migration (Stage 0)...');
        $this->newLine();

        // Initialize services
        $this->wpRepository = new WpListingRepository;
        $this->taxonomyMapper = new WpTaxonomyMapper;
        $this->migrator = new WpToCoreMigrator($this->taxonomyMapper);

        // Check database connections
        if (! $this->checkConnections()) {
            return Command::FAILURE;
        }

        // Initialize migration (create legacy source)
        $this->info('Initializing migration...');
        $this->migrator->initialize();
        $this->info('✓ Legacy source record created');
        $this->newLine();

        // Disable foreign key constraints for performance
        $this->info('Disabling foreign key constraints for bulk insert...');
        Schema::disableForeignKeyConstraints();

        try {
            // Migrate listings (organizations + venues)
            $this->migrateListings();

            // Migrate articles (if not skipped)
            if (! $this->option('skip-articles')) {
                $this->migrateArticles();
            }

            $this->newLine();
            $this->displayStatistics();
        } catch (\Exception $e) {
            $this->error("Migration failed: {$e->getMessage()}");
            $this->error($e->getTraceAsString());

            return Command::FAILURE;
        } finally {
            // Re-enable foreign key constraints
            Schema::enableForeignKeyConstraints();
            $this->info('✓ Foreign key constraints re-enabled');
        }

        return Command::SUCCESS;
    }

    /**
     * Re-process only listings whose IDs are listed in the given file (e.g. failed during a previous run).
     * Uses current migrator rules (UTF-8 sanitization, try/catch around Source creation).
     */
    private function retryFailedListings(string $filePath): int
    {
        $path = $filePath;

        if (! File::isFile($path)) {
            $this->error("File not found: {$path}");

            return Command::FAILURE;
        }

        $content = File::get($path);
        $postIds = array_values(array_unique(array_filter(
            array_map('intval', preg_split('/\s+/', trim($content), -1, PREG_SPLIT_NO_EMPTY)),
            fn ($id) => $id > 0
        )));

        if ($postIds === []) {
            $this->warn('No valid listing IDs in file.');

            return Command::SUCCESS;
        }

        $this->info('Retrying failed listings with current rules (UTF-8 sanitization, resilient Source creation)...');
        $this->info('Listing IDs: '.count($postIds));
        $this->newLine();

        $this->wpRepository = new WpListingRepository;
        $this->taxonomyMapper = new WpTaxonomyMapper;
        $this->migrator = new WpToCoreMigrator($this->taxonomyMapper);

        if (! $this->checkConnections()) {
            return Command::FAILURE;
        }

        $this->migrator->initialize();

        Schema::disableForeignKeyConstraints();

        try {
            $listings = $this->wpRepository->getListingsByPostIds($postIds);
            $bar = $this->output->createProgressBar(count($listings));
            $bar->setFormat(' %current%/%max% [%bar%] %percent:3s%%');

            foreach ($listings as $listing) {
                try {
                    $taxonomies = $this->wpRepository->getAllTaxonomiesForListing($listing->post_id);
                    $result = $this->migrator->migrateListing($listing, $taxonomies);
                    if ($result['created']) {
                        $this->organizationsCreated++;
                    } else {
                        $this->organizationsUpdated++;
                    }
                    if ($result['venue']) {
                        $this->venuesCreated++;
                    }
                } catch (\Exception $e) {
                    $this->errors++;
                    $this->warn("\nError listing ID {$listing->post_id}: {$e->getMessage()}");
                    $this->appendFailedListingId($listing->post_id, $path);
                }
                $bar->advance();
            }

            $bar->finish();
            $this->newLine(2);
            $this->displayStatistics();
        } finally {
            Schema::enableForeignKeyConstraints();
        }

        return Command::SUCCESS;
    }

    private function appendFailedListingId(int $postId, string $path): void
    {
        $dir = dirname($path);
        if (! File::isDirectory($dir)) {
            File::makeDirectory($dir, 0755, true);
        }
        File::append($path, $postId."\n");
    }

    /**
     * Check database connections.
     */
    private function checkConnections(): bool
    {
        $this->info('Checking database connections...');

        // Check Core database (default connection)
        try {
            DB::connection()->getPdo();
            $this->info('✓ Core database connected');
        } catch (\Exception $e) {
            $this->error('✗ Failed to connect to Core database: '.$e->getMessage());

            return false;
        }

        // Check WordPress database
        try {
            DB::connection('mysql_wp')->getPdo();
            $this->info('✓ WordPress database connected');
        } catch (\Exception $e) {
            $this->error('✗ Failed to connect to WordPress database: '.$e->getMessage());
            $this->warn('Make sure DB_WP_* environment variables are set in .env');

            return false;
        }

        $this->newLine();

        return true;
    }

    /**
     * Migrate WordPress listings to organizations and venues.
     */
    private function migrateListings(): void
    {
        $chunkSize = (int) $this->option('chunk-size');
        $this->info("Migrating listings (chunk size: {$chunkSize})...");

        $bar = $this->output->createProgressBar();
        $bar->setFormat(' %current%/%max% [%bar%] %percent:3s%% %elapsed:6s%/%estimated:-6s% %memory:6s%');

        $totalProcessed = 0;

        $this->wpRepository->chunkListings($chunkSize, function ($listing) use (&$totalProcessed, $bar) {
            try {
                // Get taxonomies for this listing
                $taxonomies = $this->wpRepository->getAllTaxonomiesForListing($listing->post_id);

                // Migrate listing
                $result = $this->migrator->migrateListing($listing, $taxonomies);

                if ($result['created']) {
                    $this->organizationsCreated++;
                } else {
                    $this->organizationsUpdated++;
                }

                if ($result['venue']) {
                    $this->venuesCreated++;
                }

                $totalProcessed++;
                $bar->advance();
            } catch (\Exception $e) {
                $this->errors++;
                $this->warn("\nError processing listing ID {$listing->post_id}: {$e->getMessage()}");
                $this->appendFailedListingId($listing->post_id, storage_path('logs/'.self::FAILED_LISTINGS_FILE));
            }
        });

        // Get total count for progress bar
        $totalCount = DB::connection('mysql_wp')
            ->table('posts')
            ->where('post_type', 'hp_listing')
            ->where('post_status', 'publish')
            ->count();

        $bar->setMaxSteps($totalCount);
        $bar->finish();
        $this->newLine(2);
    }

    /**
     * Migrate WordPress posts to articles.
     */
    private function migrateArticles(): void
    {
        $chunkSize = (int) $this->option('chunk-size');
        $this->info("Migrating articles (chunk size: {$chunkSize})...");

        $bar = $this->output->createProgressBar();
        $bar->setFormat(' %current%/%max% [%bar%] %percent:3s%% %elapsed:6s%/%estimated:-6s% %memory:6s%');

        $totalProcessed = 0;

        $this->wpRepository->chunkArticles($chunkSize, function ($post) use (&$totalProcessed, $bar) {
            try {
                $article = $this->migrator->migrateArticle($post);

                if ($article && $article->wasRecentlyCreated) {
                    $this->articlesCreated++;
                }

                $totalProcessed++;
                $bar->advance();
            } catch (\Exception $e) {
                $this->errors++;
                $this->warn("\nError processing article ID {$post->ID}: {$e->getMessage()}");
            }
        });

        // Get total count for progress bar
        $totalCount = DB::connection('mysql_wp')
            ->table('posts')
            ->where('post_type', 'post')
            ->where('post_status', 'publish')
            ->count();

        $bar->setMaxSteps($totalCount);
        $bar->finish();
        $this->newLine(2);
    }

    /**
     * Display migration statistics.
     */
    private function displayStatistics(): void
    {
        $this->info('Migration completed!');
        $this->newLine();
        $this->table(
            ['Metric', 'Count'],
            [
                ['Organizations created', $this->organizationsCreated],
                ['Organizations updated', $this->organizationsUpdated],
                ['Venues created', $this->venuesCreated],
                ['Articles created', $this->articlesCreated],
                ['Errors', $this->errors],
            ]
        );
    }
}
