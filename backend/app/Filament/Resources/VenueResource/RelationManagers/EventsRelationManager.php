<?php

namespace App\Filament\Resources\VenueResource\RelationManagers;

use App\Filament\Resources\EventResource;
use App\Filament\Support\StatusColors;
use Filament\Resources\RelationManagers\RelationManager;
use Filament\Tables;
use Filament\Tables\Actions\AttachAction;
use Filament\Tables\Table;

class EventsRelationManager extends RelationManager
{
    protected static string $relationship = 'events';

    public function table(Table $table): Table
    {
        return $table
            ->recordTitleAttribute('title')
            ->columns([
                Tables\Columns\TextColumn::make('title')
                    ->searchable(),
                Tables\Columns\TextColumn::make('status')
                    ->badge()
                    ->color(fn (?string $state): string => StatusColors::badgeColor($state)),
            ])
            ->headerActions([
                AttachAction::make()
                    ->multiple()
                    ->preloadRecordSelect(),
            ])
            ->actions([
                Tables\Actions\Action::make('open')
                    ->url(fn ($record): string => EventResource::getUrl('edit', ['record' => $record]))
                    ->icon('heroicon-o-arrow-top-right-on-square'),
                Tables\Actions\DetachAction::make(),
            ])
            ->bulkActions([
                Tables\Actions\BulkActionGroup::make([
                    Tables\Actions\DetachBulkAction::make(),
                ]),
            ]);
    }
}
