<?php

namespace App\Filament\Resources;

use App\Filament\Resources\ParseProfileResource\Pages;
use App\Models\ParseProfile;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;

class ParseProfileResource extends Resource
{
    protected static ?string $model = ParseProfile::class;

    protected static ?string $navigationIcon = 'heroicon-o-cog-6-tooth';

    protected static ?string $navigationGroup = 'Harvester';

    protected static ?int $navigationSort = 42;

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\Select::make('source_id')
                    ->relationship('source', 'name')
                    ->searchable()
                    ->required(),
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

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('source.name')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('entity_type'),
                Tables\Columns\TextColumn::make('crawl_strategy'),
                Tables\Columns\IconColumn::make('is_active')
                    ->boolean(),
                Tables\Columns\TextColumn::make('updated_at')
                    ->dateTime()
                    ->sortable(),
            ])
            ->defaultSort('updated_at', 'desc')
            ->filters([
                Tables\Filters\TernaryFilter::make('is_active'),
            ])
            ->actions([
                Tables\Actions\EditAction::make(),
            ])
            ->bulkActions([
                Tables\Actions\BulkActionGroup::make([
                    Tables\Actions\DeleteBulkAction::make(),
                ]),
            ]);
    }

    public static function getRelations(): array
    {
        return [];
    }

    public static function getPages(): array
    {
        return [
            'index' => Pages\ListParseProfiles::route('/'),
            'create' => Pages\CreateParseProfile::route('/create'),
            'edit' => Pages\EditParseProfile::route('/{record}/edit'),
        ];
    }
}
