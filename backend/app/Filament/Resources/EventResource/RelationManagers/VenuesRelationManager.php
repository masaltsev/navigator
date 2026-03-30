<?php

namespace App\Filament\Resources\EventResource\RelationManagers;

use Filament\Resources\RelationManagers\RelationManager;
use Filament\Tables;
use Filament\Tables\Actions\AttachAction;
use Filament\Tables\Table;

class VenuesRelationManager extends RelationManager
{
    protected static string $relationship = 'venues';

    public function table(Table $table): Table
    {
        return $table
            ->recordTitleAttribute('address_raw')
            ->columns([
                Tables\Columns\TextColumn::make('address_raw')
                    ->searchable(),
                Tables\Columns\TextColumn::make('region_iso'),
            ])
            ->headerActions([
                AttachAction::make()
                    ->multiple()
                    ->preloadRecordSelect(),
            ])
            ->actions([
                Tables\Actions\DetachAction::make(),
            ])
            ->bulkActions([
                Tables\Actions\BulkActionGroup::make([
                    Tables\Actions\DetachBulkAction::make(),
                ]),
            ]);
    }
}
