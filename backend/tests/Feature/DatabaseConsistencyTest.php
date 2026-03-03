<?php

use App\Services\DatabaseConsistencyReport;
use Illuminate\Support\Facades\DB;

/**
 * Ideal structure: Organization (1) -> Organizer (1) -> 1 Venue + 1 Source (kind=org_website).
 * Run `php artisan db:consistency-report` for the report against the real database.
 * This test runs only when using PostgreSQL (migrations use PostGIS); skipped on sqlite.
 */
test('database consistency report: ideal vs partial organization-organizer-venue-source matches', function () {
    $driver = DB::connection()->getDriverName();
    if ($driver !== 'pgsql') {
        expect(true)->toBeTrue();

        return;
    }

    $report = (new DatabaseConsistencyReport)->run();

    expect($report['total'])->toBe($report['ideal'] + $report['partial'])
        ->and($report['breakdown'])->toHaveKeys([
            'no_organizer',
            'organizer_but_no_venue',
            'organizer_but_multiple_venues',
            'organizer_but_no_org_website_source',
            'organizer_but_multiple_org_website_sources',
            'ideal',
        ]);

    // Expose counts when running the test
    echo "\n--- Database consistency (approved organizations) ---\n";
    echo "Total: {$report['total']}\n";
    echo "Ideal (1 org -> 1 organizer -> 1 venue + 1 org_website source): {$report['ideal']}\n";
    echo "Partial: {$report['partial']}\n";
    echo "Breakdown:\n";
    foreach ($report['breakdown'] as $key => $count) {
        echo "  - {$key}: {$count}\n";
    }
    echo "---\n";
});
