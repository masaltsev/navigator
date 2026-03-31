<?php

use App\Models\Organization;
use App\Services\Import\ImportMergeService;
use Tests\Concerns\RefreshDatabaseWithSchema;
use Tests\TestCase;

uses(TestCase::class, RefreshDatabaseWithSchema::class);

test('mergeAttributes keeps title and legal ids when organization has both inn and ogrn unless incoming is verified', function (): void {
    if (config('database.connections.pgsql.database') === 'navigator_core') {
        $this->markTestSkipped('Refusing to write to production database from tests.');
    }

    $org = Organization::factory()->create([
        'title' => 'Canonical Title',
        'short_title' => 'CT',
        'inn' => '1234567890',
        'ogrn' => '1234567890123',
        'verified_fields' => [],
    ]);

    $service = new ImportMergeService;
    $merged = $service->mergeAttributes($org, [
        'title' => 'Crawler Title',
        'short_title' => 'XX',
        'inn' => '9999999999',
        'ogrn' => '9999999999999',
        'description' => 'New description',
    ], incomingVerified: []);

    expect($merged['title'])->toBe('Canonical Title')
        ->and($merged['short_title'])->toBe('CT')
        ->and($merged['inn'])->toBe('1234567890')
        ->and($merged['ogrn'])->toBe('1234567890123')
        ->and($merged['description'])->toBe('New description');
});
