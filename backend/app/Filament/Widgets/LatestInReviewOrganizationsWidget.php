<?php

namespace App\Filament\Widgets;

use App\Filament\Resources\OrganizationResource;
use App\Models\Organization;
use Filament\Tables;
use Filament\Tables\Table;
use Filament\Widgets\TableWidget as BaseWidget;

class LatestInReviewOrganizationsWidget extends BaseWidget
{
    protected static ?int $sort = 1;

    protected int|string|array $columnSpan = 'full';

    public function table(Table $table): Table
    {
        return $table
            ->heading('Organizations in review')
            ->query(
                Organization::query()
                    ->where('status', 'in_review')
                    ->latest('updated_at')
                    ->limit(10)
            )
            ->columns([
                Tables\Columns\TextColumn::make('title')
                    ->url(fn (Organization $record): string => OrganizationResource::getUrl('edit', ['record' => $record])),
                Tables\Columns\TextColumn::make('inn'),
                Tables\Columns\TextColumn::make('updated_at')
                    ->dateTime(),
            ])
            ->paginated(false);
    }
}
