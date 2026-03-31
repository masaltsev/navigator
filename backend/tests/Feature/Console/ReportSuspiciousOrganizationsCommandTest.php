<?php

use Tests\Concerns\RefreshDatabaseWithSchema;

uses(RefreshDatabaseWithSchema::class);

test('db:report-suspicious-organizations runs successfully', function (): void {
    if (config('database.connections.pgsql.database') === 'navigator_core') {
        $this->markTestSkipped('Refusing to run report against production database from tests.');
    }

    $this->artisan('db:report-suspicious-organizations')
        ->assertSuccessful();
});
