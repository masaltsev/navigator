<?php

use Tests\Concerns\RefreshDatabaseWithSchema;

uses(RefreshDatabaseWithSchema::class);

test('db:cleanup-test-records refuses to run without --dry-run or --force', function (): void {
    if (config('database.default') !== 'pgsql') {
        $this->markTestSkipped('Command uses PostgreSQL regex.');
    }

    $this->artisan('db:cleanup-test-records')
        ->assertFailed();
});

test('db:cleanup-test-records dry-run succeeds', function (): void {
    if (config('database.default') !== 'pgsql') {
        $this->markTestSkipped('Command uses PostgreSQL regex.');
    }

    $this->artisan('db:cleanup-test-records', ['--dry-run' => true])
        ->assertSuccessful();
});
