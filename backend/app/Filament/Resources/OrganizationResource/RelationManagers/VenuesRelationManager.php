<?php

namespace App\Filament\Resources\OrganizationResource\RelationManagers;

use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\RelationManagers\RelationManager;
use Filament\Tables;
use Filament\Tables\Actions\AttachAction;
use Filament\Tables\Table;

class VenuesRelationManager extends RelationManager
{
    protected static string $relationship = 'venues';

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\TextInput::make('address_raw')
                    ->required()
                    ->maxLength(255),
            ]);
    }

    public function table(Table $table): Table
    {
        return $table
            ->recordTitleAttribute('address_raw')
            ->columns([
                Tables\Columns\TextColumn::make('address_raw')
                    ->searchable(),
                Tables\Columns\IconColumn::make('pivot.is_headquarters')
                    ->label('HQ')
                    ->boolean(),
                Tables\Columns\TextColumn::make('region_iso'),
            ])
            ->headerActions([
                AttachAction::make()
                    ->multiple()
                    ->preloadRecordSelect()
                    ->form(fn (AttachAction $action): array => [
                        $action->getRecordSelect(),
                        Forms\Components\Toggle::make('is_headquarters')
                            ->default(false),
                    ]),
            ])
            ->actions([
                Tables\Actions\Action::make('toggleHeadquarters')
                    ->label('Toggle HQ')
                    ->icon('heroicon-m-building-office')
                    ->action(function ($record): void {
                        $record->pivot->update([
                            'is_headquarters' => ! (bool) $record->pivot->is_headquarters,
                        ]);
                    }),
                Tables\Actions\DetachAction::make(),
            ])
            ->bulkActions([
                Tables\Actions\BulkActionGroup::make([
                    Tables\Actions\DetachBulkAction::make(),
                ]),
            ]);
    }
}
