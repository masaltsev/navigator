<?php

namespace App\Filament\Widgets;

use App\Models\Article;
use App\Models\Event;
use App\Models\Organization;
use App\Models\Source;
use App\Models\User;
use Filament\Widgets\StatsOverviewWidget as BaseWidget;
use Filament\Widgets\StatsOverviewWidget\Stat;

class NavigatorStatsOverview extends BaseWidget
{
    protected static ?int $sort = 0;

    protected function getStats(): array
    {
        return [
            Stat::make('Organizations', (string) Organization::query()->count()),
            Stat::make('Events', (string) Event::query()->count()),
            Stat::make('Sources', (string) Source::query()->count()),
            Stat::make('Articles', (string) Article::query()->count()),
            Stat::make('Users', (string) User::query()->count()),
        ];
    }
}
