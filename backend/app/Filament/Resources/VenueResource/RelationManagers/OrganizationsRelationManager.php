<?php

namespace App\Filament\Resources\VenueResource\RelationManagers;

use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\RelationManagers\RelationManager;
use Filament\Tables;
use Filament\Tables\Actions\AttachAction;
use Filament\Tables\Table;

class OrganizationsRelationManager extends RelationManager
{
    protected static string $relationship = 'organizations';

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\TextInput::make('title')
                    ->required()
                    ->maxLength(255),
            ]);
    }

    public function table(Table $table): Table
    {
        return $table
            ->recordTitleAttribute('title')
            ->columns([
                Tables\Columns\TextColumn::make('title')
                    ->searchable(),
                Tables\Columns\IconColumn::make('pivot.is_headquarters')
                    ->label('HQ')
                    ->boolean(),
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
