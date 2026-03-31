<?php

namespace Tests\Concerns;

use Illuminate\Foundation\Testing\RefreshDatabase;

trait RefreshDatabaseWithSchema
{
    use RefreshDatabase {
        migrateFreshUsing as baseMigrateFreshUsing;
    }

    protected function migrateDatabases()
    {
        $options = $this->baseMigrateFreshUsing();

        $connectionName = config('database.default');
        $driver = is_string($connectionName) ? config("database.connections.{$connectionName}.driver") : null;

        if ($driver === 'pgsql') {
            $schemaPath = database_path('schema/pgsql-schema.sql');

            if (is_file($schemaPath)) {
                $options['--schema-path'] = $schemaPath;
            }

            $options['--force'] = true;
        }

        $this->artisan('migrate:fresh', $options);
    }
}

