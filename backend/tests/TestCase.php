<?php

namespace Tests;

use RuntimeException;
use Illuminate\Contracts\Console\Kernel;
use Illuminate\Foundation\Testing\RefreshDatabaseState;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    protected bool $seed = true;

    protected function assertSafeTestDatabase(): void
    {
        if (config('app.env') !== 'testing') {
            return;
        }

        $connectionName = config('database.default');

        if (! is_string($connectionName) || $connectionName === '') {
            throw new RuntimeException('Test database safety check failed: database.default is not a string.');
        }

        $driver = config("database.connections.{$connectionName}.driver");

        if ($driver !== 'pgsql') {
            return;
        }

        $database = config("database.connections.{$connectionName}.database");

        if (! is_string($database) || $database === '') {
            throw new RuntimeException('Test database safety check failed: pgsql database name is missing.');
        }

        if ($database === 'navigator_core' || ! str_ends_with($database, '_test')) {
            throw new RuntimeException("Refusing to run tests with destructive migrations on non-test database [{$database}]. Expected *_test.");
        }
    }

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

        $this->assertSafeTestDatabase();

        $schemaPath = database_path('schema/pgsql-schema.sql');

        $this->artisan('migrate:fresh', [
            '--seed' => true,
            '--force' => true,
        ]);

        $this->app[Kernel::class]->setArtisan(null);

        RefreshDatabaseState::$migrated = true;
    }
}
