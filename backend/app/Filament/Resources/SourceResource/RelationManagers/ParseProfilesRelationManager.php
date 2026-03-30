<?php

namespace App\Filament\Resources\SourceResource\RelationManagers;

use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\RelationManagers\RelationManager;
use Filament\Tables;
use Filament\Tables\Table;

class ParseProfilesRelationManager extends RelationManager
{
    protected static string $relationship = 'parseProfiles';

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\TextInput::make('entity_type')
                    ->required()
                    ->maxLength(255),
                Forms\Components\TextInput::make('crawl_strategy')
                    ->required()
                    ->maxLength(255),
                Forms\Components\KeyValue::make('config')
                    ->required(),
                Forms\Components\Toggle::make('is_active')
                    ->default(true),
            ]);
    }

    public function table(Table $table): Table
    {
        return $table
            ->recordTitleAttribute('entity_type')
            ->columns([
                Tables\Columns\TextColumn::make('entity_type'),
                Tables\Columns\TextColumn::make('crawl_strategy'),
                Tables\Columns\IconColumn::make('is_active')
                    ->boolean(),
                Tables\Columns\TextColumn::make('updated_at')
                    ->dateTime()
                    ->sortable(),
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
