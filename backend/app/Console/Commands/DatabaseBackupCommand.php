<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;
use Symfony\Component\Process\Process;

/**
 * Plain SQL dump compressed with gzip for rollback after nightly harvest runs.
 */
class DatabaseBackupCommand extends Command
{
    protected $signature = 'db:backup
                            {--path= : Override backup directory (default: config backup.database_directory)}';

    protected $description = 'Create a gzipped PostgreSQL dump (not for git; keep outside web root).';

    public function handle(): int
    {
        if (config('database.default') !== 'pgsql') {
            $this->error('db:backup only supports the pgsql connection (current: '.config('database.default').').');

            return self::FAILURE;
        }

        $pgDump = $this->findPgDump();
        if ($pgDump === null) {
            $this->error('pg_dump not found in PATH (install postgresql-client).');

            return self::FAILURE;
        }

        $db = config('database.connections.pgsql');
        $dir = $this->option('path') ?: config('backup.database_directory');
        $retentionDays = max(1, (int) config('backup.retention_days'));

        if (! is_dir($dir)) {
            File::makeDirectory($dir, 0700, true);
        }

        $timestamp = now()->format('Y-m-d_His');
        $filename = "navigator_{$timestamp}.sql.gz";
        $fullPath = rtrim($dir, '/').'/'.$filename;

        $tmpBase = tempnam(sys_get_temp_dir(), 'navpg_');
        if ($tmpBase === false) {
            $this->error('Could not create temp file.');

            return self::FAILURE;
        }

        unlink($tmpBase);
        $tmpSql = $tmpBase.'.sql';

        $dump = new Process(
            [
                $pgDump,
                '-h', $db['host'] ?? '127.0.0.1',
                '-p', (string) ($db['port'] ?? 5432),
                '-U', $db['username'] ?? 'postgres',
                '-d', $db['database'] ?? 'postgres',
                '--no-owner',
                '--no-acl',
                '-f', $tmpSql,
            ],
            null,
            ['PGPASSWORD' => (string) ($db['password'] ?? '')],
            null,
            3600
        );

        $this->info('Running pg_dump…');

        try {
            $dump->mustRun();
        } catch (\Throwable $e) {
            if (is_file($tmpSql)) {
                @unlink($tmpSql);
            }
            $this->error('pg_dump failed: '.$e->getMessage());

            return self::FAILURE;
        }

        $gzip = new Process(['gzip', '-9', '-n', $tmpSql], null, null, null, 3600);

        try {
            $gzip->mustRun();
        } catch (\Throwable $e) {
            if (is_file($tmpSql)) {
                @unlink($tmpSql);
            }
            $this->error('gzip failed: '.$e->getMessage());

            return self::FAILURE;
        }

        $gzPath = $tmpSql.'.gz';
        if (! is_file($gzPath)) {
            $this->error('Expected '.$gzPath.' after gzip.');

            return self::FAILURE;
        }

        if (! @rename($gzPath, $fullPath)) {
            @unlink($gzPath);
            $this->error('Could not move dump to '.$fullPath);

            return self::FAILURE;
        }

        @chmod($fullPath, 0600);

        $this->info('Backup written: '.$fullPath);

        $this->pruneOldBackups($dir, $retentionDays);

        return self::SUCCESS;
    }

    private function findPgDump(): ?string
    {
        $which = new Process(['which', 'pg_dump']);
        $which->run();

        if ($which->isSuccessful() && is_executable(trim($which->getOutput()))) {
            return trim($which->getOutput());
        }

        $candidates = ['/usr/bin/pg_dump', '/usr/local/bin/pg_dump'];
        foreach ($candidates as $path) {
            if (is_executable($path)) {
                return $path;
            }
        }

        return null;
    }

    private function pruneOldBackups(string $dir, int $retentionDays): void
    {
        $cutoff = now()->subDays($retentionDays)->getTimestamp();
        $removed = 0;

        foreach (File::files($dir) as $file) {
            $name = $file->getFilename();
            if (! str_ends_with($name, '.sql.gz')) {
                continue;
            }
            if ($file->getMTime() >= $cutoff) {
                continue;
            }
            File::delete($file->getPathname());
            $removed++;
        }

        if ($removed > 0) {
            $this->info("Removed {$removed} backup(s) older than {$retentionDays} days.");
        }
    }
}
