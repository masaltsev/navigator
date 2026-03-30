<?php

namespace App\Filament\Widgets;

use App\Filament\Resources\SourceResource;
use App\Models\Source;
use Filament\Tables;
use Filament\Tables\Table;
use Filament\Widgets\TableWidget as BaseWidget;

class LatestCrawledSourcesWidget extends BaseWidget
{
    protected static ?int $sort = 2;

    protected int|string|array $columnSpan = 'full';

    public function table(Table $table): Table
    {
        return $table
            ->heading('Recently crawled sources')
            ->query(
                Source::query()
                    ->whereNotNull('last_crawled_at')
                    ->orderByDesc('last_crawled_at')
                    ->limit(10)
            )
            ->columns([
                Tables\Columns\TextColumn::make('name')
                    ->url(fn (Source $record): string => SourceResource::getUrl('edit', ['record' => $record])),
                Tables\Columns\TextColumn::make('kind')
                    ->badge(),
                Tables\Columns\TextColumn::make('last_status')
                    ->badge(),
                Tables\Columns\TextColumn::make('last_crawled_at')
                    ->dateTime(),
            ])
            ->paginated(false);
    }
}
