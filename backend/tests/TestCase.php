<?php

namespace Tests;

use Illuminate\Contracts\Console\Kernel;
use Illuminate\Foundation\Testing\RefreshDatabaseState;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    protected bool $seed = true;

    protected function setUp(): void
    {
        parent::setUp();

        $connectionName = config('database.default');
        $driver = is_string($connectionName) ? config("database.connections.{$connectionName}.driver") : null;

        if ($driver !== 'pgsql') {
            return;
        }

        if (RefreshDatabaseState::$migrated) {
            return;
        }

        $schemaPath = database_path('schema/pgsql-schema.sql');

        $this->artisan('migrate:fresh', [
            '--schema-path' => is_file($schemaPath) ? $schemaPath : null,
            '--seed' => true,
            '--force' => true,
        ]);

        $this->app[Kernel::class]->setArtisan(null);

        RefreshDatabaseState::$migrated = true;
    }
}
