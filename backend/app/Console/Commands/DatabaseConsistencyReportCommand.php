<?php

namespace App\Console\Commands;

use App\Services\DatabaseConsistencyReport;
use Illuminate\Console\Command;

class DatabaseConsistencyReportCommand extends Command
{
    protected $signature = 'db:consistency-report';

    protected $description = 'Report consistency: ideal (1 org -> 1 organizer -> 1 venue + 1 org_website source) vs partial';

    public function handle(): int
    {
        $report = (new DatabaseConsistencyReport)->run();

        $this->info('Database consistency (approved organizations)');
        $this->newLine();
        $this->table(
            ['Metric', 'Count'],
            [
                ['Total', $report['total']],
                ['Ideal (1 org → 1 organizer → 1 venue + 1 org_website source)', $report['ideal']],
                ['Partial', $report['partial']],
            ]
        );
        $this->newLine();
        $this->info('Breakdown (partials):');
        $this->table(
            ['Case', 'Count'],
            collect($report['breakdown'])
                ->reject(fn ($count, $key) => $key === 'ideal')
                ->map(fn ($count, $key) => [$key, $count])
                ->values()
                ->all()
        );
        $this->line("  ideal: {$report['breakdown']['ideal']}");

        return self::SUCCESS;
    }
}
