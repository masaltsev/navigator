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
| Runs daily at 02:00. Requires HARVESTER_URL and HARVESTER_API_TOKEN in .env.
| On production ensure cron: * * * * * cd /path/to/backend && php artisan schedule:run
*/
Schedule::command('harvest:dispatch-due', ['--limit' => 500])->daily()->at('02:00');
