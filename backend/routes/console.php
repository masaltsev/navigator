<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Schedule;

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote');

/*
|--------------------------------------------------------------------------
| Harvester: dispatch due sources to crawl (POST /harvest/run)
|--------------------------------------------------------------------------
| DISABLED: nightly harvest was unreliable on prod; run manually when ready:
|   php artisan harvest:dispatch-due [--limit=100] [--dry-run]
| Requires HARVESTER_URL and HARVESTER_API_TOKEN in .env.
| Cron must still run schedule:run for other tasks, e.g. db:backup.
*/
/*
|--------------------------------------------------------------------------
| Database backup before nightly harvest (rollback safety)
|--------------------------------------------------------------------------
| Runs five minutes before harvest. Dumps live under DB_BACKUP_DIRECTORY
| (default: /home/deploy/backups/navigator), not in git or nginx docroot.
*/
Schedule::command('db:backup')->daily()->at('01:55');

// Schedule::command('harvest:dispatch-due', ['--limit' => 500])->daily()->at('02:00');
