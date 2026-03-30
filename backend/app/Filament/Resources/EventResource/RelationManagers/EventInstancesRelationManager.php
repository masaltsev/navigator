<?php

namespace App\Filament\Resources\EventResource\RelationManagers;

use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\RelationManagers\RelationManager;
use Filament\Tables;
use Filament\Tables\Table;

class EventInstancesRelationManager extends RelationManager
{
    protected static string $relationship = 'instances';

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\DateTimePicker::make('start_datetime')
                    ->required()
                    ->seconds(false),
                Forms\Components\DateTimePicker::make('end_datetime')
                    ->required()
                    ->seconds(false),
                Forms\Components\Select::make('status')
                    ->options([
                        'scheduled' => 'Scheduled',
                        'cancelled' => 'Cancelled',
                        'rescheduled' => 'Rescheduled',
                        'finished' => 'Finished',
                    ])
                    ->required()
                    ->native(false),
            ]);
    }

    public function table(Table $table): Table
    {
        return $table
            ->recordTitleAttribute('start_datetime')
            ->columns([
                Tables\Columns\TextColumn::make('start_datetime')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('end_datetime')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('status')
                    ->badge(),
            ])
            ->headerActions([
                Tables\Actions\CreateAction::make(),
            ])
            ->actions([
                Tables\Actions\EditAction::make(),
                Tables\Actions\DeleteAction::make(),
            ])
            ->bulkActions([
                Tables\Actions\BulkActionGroup::make([
                    Tables\Actions\DeleteBulkAction::make(),
                ]),
            ]);
    }
}
