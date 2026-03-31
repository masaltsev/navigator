<?php

use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

test('db:report-suspicious-organizations runs successfully', function (): void {
    if (config('database.connections.pgsql.database') === 'navigator_core') {
        $this->markTestSkipped('Refusing to run report against production database from tests.');
    }

    $this->artisan('db:report-suspicious-organizations')
        ->assertSuccessful();
});
