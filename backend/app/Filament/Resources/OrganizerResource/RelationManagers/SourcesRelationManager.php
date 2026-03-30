<?php

namespace App\Filament\Resources\OrganizerResource\RelationManagers;

use App\Models\Source;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\RelationManagers\RelationManager;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\SoftDeletingScope;

class SourcesRelationManager extends RelationManager
{
    protected static string $relationship = 'sources';

    public function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\TextInput::make('name')
                    ->required()
                    ->maxLength(255),
                Forms\Components\Select::make('kind')
                    ->options(array_combine(Source::KINDS, Source::KINDS))
                    ->required()
                    ->native(false),
                Forms\Components\TextInput::make('base_url')
                    ->required()
                    ->url()
                    ->maxLength(65535),
                Forms\Components\TagsInput::make('entry_points')
                    ->placeholder('Entry point URL'),
                Forms\Components\TextInput::make('region_iso')
                    ->maxLength(255),
                Forms\Components\TextInput::make('crawl_period_days')
                    ->numeric()
                    ->default(7),
                Forms\Components\TextInput::make('priority')
                    ->numeric()
                    ->default(50),
                Forms\Components\Toggle::make('is_active')
                    ->default(true),
            ]);
    }

    public function table(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn (Builder $query) => $query->withoutGlobalScopes([SoftDeletingScope::class]))
            ->recordTitleAttribute('name')
            ->columns([
                Tables\Columns\TextColumn::make('name')
                    ->searchable(),
                Tables\Columns\TextColumn::make('kind')
                    ->badge(),
                Tables\Columns\TextColumn::make('base_url')
                    ->limit(40),
                Tables\Columns\IconColumn::make('is_active')
                    ->boolean(),
                Tables\Columns\TextColumn::make('last_status')
                    ->badge(),
                Tables\Columns\TextColumn::make('last_crawled_at')
                    ->dateTime()
                    ->sortable(),
            ])
            ->headerActions([
                Tables\Actions\CreateAction::make(),
            ])
            ->actions([
                Tables\Actions\EditAction::make(),
                Tables\Actions\DeleteAction::make(),
                Tables\Actions\ForceDeleteAction::make(),
                Tables\Actions\RestoreAction::make(),
            ])
            ->bulkActions([
                Tables\Actions\BulkActionGroup::make([
                    Tables\Actions\DeleteBulkAction::make(),
                    Tables\Actions\ForceDeleteBulkAction::make(),
                    Tables\Actions\RestoreBulkAction::make(),
                ]),
            ]);
    }
}
