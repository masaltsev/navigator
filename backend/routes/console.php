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
| Uncomment to run daily. Requires HARVESTER_URL and HARVESTER_API_TOKEN.
*/
// Schedule::command('harvest:dispatch-due', ['--limit' => 100])->daily()->at('02:00');
