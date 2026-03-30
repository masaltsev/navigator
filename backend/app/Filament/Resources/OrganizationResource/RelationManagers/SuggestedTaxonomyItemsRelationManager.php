<?php

namespace App\Filament\Resources\OrganizationResource\RelationManagers;

use App\Filament\Support\StatusColors;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\RelationManagers\RelationManager;
use Filament\Tables;
use Filament\Tables\Table;

class SuggestedTaxonomyItemsRelationManager extends RelationManager
{
    protected static string $relationship = 'suggestedTaxonomyItems';

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\TextInput::make('dictionary_type')
                    ->required()
                    ->maxLength(255),
                Forms\Components\TextInput::make('suggested_name')
                    ->required()
                    ->maxLength(255),
                Forms\Components\TextInput::make('source_reference')
                    ->maxLength(255),
                Forms\Components\Textarea::make('ai_reasoning')
                    ->columnSpanFull(),
                Forms\Components\Select::make('status')
                    ->options([
                        'pending' => 'Pending',
                        'approved' => 'Approved',
                        'rejected' => 'Rejected',
                    ])
                    ->required()
                    ->native(false),
            ]);
    }

    public function table(Table $table): Table
    {
        return $table
            ->recordTitleAttribute('suggested_name')
            ->columns([
                Tables\Columns\TextColumn::make('dictionary_type'),
                Tables\Columns\TextColumn::make('suggested_name')
                    ->searchable(),
                Tables\Columns\TextColumn::make('status')
                    ->badge()
                    ->color(fn (?string $state): string => StatusColors::badgeColor($state)),
                Tables\Columns\TextColumn::make('created_at')
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
