<?php

namespace Tests\Concerns;

use RuntimeException;
use Illuminate\Foundation\Testing\RefreshDatabase;

trait RefreshDatabaseWithSchema
{
    use RefreshDatabase {
        migrateFreshUsing as baseMigrateFreshUsing;
    }

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
            throw new RuntimeException("Refusing to run migrate:fresh on non-test database [{$database}]. Expected *_test.");
        }
    }

    protected function migrateDatabases()
    {
        $this->assertSafeTestDatabase();

        $options = $this->baseMigrateFreshUsing();

        $connectionName = config('database.default');
        $driver = is_string($connectionName) ? config("database.connections.{$connectionName}.driver") : null;

        if ($driver === 'pgsql') {
            $options['--force'] = true;
        }

        $this->artisan('migrate:fresh', $options);
    }
}

