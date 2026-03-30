<?php

namespace App\Filament\Resources;

use App\Filament\Resources\SuggestedTaxonomyItemResource\Pages;
use App\Filament\Support\StatusColors;
use App\Models\SuggestedTaxonomyItem;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Actions\BulkAction;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Collection;

class SuggestedTaxonomyItemResource extends Resource
{
    protected static ?string $model = SuggestedTaxonomyItem::class;

    protected static ?string $navigationIcon = 'heroicon-o-sparkles';

    protected static ?string $navigationGroup = 'Harvester';

    protected static ?int $navigationSort = 43;

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\Select::make('organization_id')
                    ->relationship('organization', 'title')
                    ->searchable()
                    ->required(),
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

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('organization.title')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('dictionary_type'),
                Tables\Columns\TextColumn::make('suggested_name')
                    ->searchable(),
                Tables\Columns\TextColumn::make('status')
                    ->badge()
                    ->color(fn (?string $state): string => StatusColors::badgeColor($state)),
                Tables\Columns\TextColumn::make('ai_reasoning')
                    ->limit(50)
                    ->tooltip(fn (SuggestedTaxonomyItem $record): ?string => $record->ai_reasoning),
                Tables\Columns\TextColumn::make('created_at')
                    ->dateTime()
                    ->sortable(),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                Tables\Filters\SelectFilter::make('status')
                    ->options([
                        'pending' => 'Pending',
                        'approved' => 'Approved',
                        'rejected' => 'Rejected',
                    ]),
                Tables\Filters\SelectFilter::make('dictionary_type')
                    ->options(fn (): array => SuggestedTaxonomyItem::query()
                        ->whereNotNull('dictionary_type')
                        ->distinct()
                        ->orderBy('dictionary_type')
                        ->pluck('dictionary_type', 'dictionary_type')
                        ->all()),
            ])
            ->actions([
                Tables\Actions\Action::make('approve')
                    ->icon('heroicon-o-check')
                    ->color('success')
                    ->visible(fn (SuggestedTaxonomyItem $r): bool => $r->status !== 'approved')
                    ->action(fn (SuggestedTaxonomyItem $r) => $r->update(['status' => 'approved'])),
                Tables\Actions\Action::make('reject')
                    ->icon('heroicon-o-x-mark')
                    ->color('danger')
                    ->visible(fn (SuggestedTaxonomyItem $r): bool => $r->status !== 'rejected')
                    ->action(fn (SuggestedTaxonomyItem $r) => $r->update(['status' => 'rejected'])),
                Tables\Actions\EditAction::make(),
            ])
            ->bulkActions([
                Tables\Actions\BulkActionGroup::make([
                    BulkAction::make('approve')
                        ->icon('heroicon-o-check')
                        ->color('success')
                        ->action(fn (Collection $records) => $records->each->update(['status' => 'approved'])),
                    BulkAction::make('reject')
                        ->icon('heroicon-o-x-mark')
                        ->color('danger')
                        ->action(fn (Collection $records) => $records->each->update(['status' => 'rejected'])),
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
            'index' => Pages\ListSuggestedTaxonomyItems::route('/'),
            'create' => Pages\CreateSuggestedTaxonomyItem::route('/create'),
            'edit' => Pages\EditSuggestedTaxonomyItem::route('/{record}/edit'),
        ];
    }
}
