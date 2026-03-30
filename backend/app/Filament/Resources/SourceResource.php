<?php

namespace App\Filament\Resources;

use App\Filament\Resources\SourceResource\Pages;
use App\Filament\Resources\SourceResource\RelationManagers;
use App\Models\Organizer;
use App\Models\Source;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\SoftDeletingScope;

class SourceResource extends Resource
{
    protected static ?string $model = Source::class;

    protected static ?string $navigationIcon = 'heroicon-o-arrow-path';

    protected static ?string $navigationGroup = 'Harvester';

    protected static ?int $navigationSort = 40;

    protected static ?string $recordTitleAttribute = 'name';

    /**
     * @return array<int, string>
     */
    public static function getGloballySearchableAttributes(): array
    {
        return ['name', 'base_url'];
    }

    public static function form(Form $form): Form
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
                Forms\Components\Textarea::make('base_url')
                    ->required()
                    ->rows(2),
                Forms\Components\TagsInput::make('entry_points')
                    ->placeholder('Entry point'),
                Forms\Components\Select::make('organizer_id')
                    ->label('Organizer')
                    ->options(function (): array {
                        return Organizer::query()
                            ->with('organizable')
                            ->orderBy('id')
                            ->get()
                            ->mapWithKeys(function (Organizer $o): array {
                                $label = match ($o->organizable_type) {
                                    'Organization' => $o->organizable?->title ?? $o->id,
                                    'InitiativeGroup' => $o->organizable?->name ?? $o->id,
                                    'Individual' => $o->organizable?->full_name ?? $o->id,
                                    default => (string) $o->id,
                                };

                                return [$o->id => $label];
                            })
                            ->all();
                    })
                    ->searchable(),
                Forms\Components\TextInput::make('region_iso')
                    ->maxLength(255),
                Forms\Components\TextInput::make('fias_region_id')
                    ->maxLength(36)
                    ->nullable(),
                Forms\Components\TextInput::make('crawl_period_days')
                    ->numeric()
                    ->default(7),
                Forms\Components\TextInput::make('priority')
                    ->numeric()
                    ->default(50),
                Forms\Components\Toggle::make('is_active')
                    ->default(true),
                Forms\Components\TextInput::make('last_status')
                    ->disabled()
                    ->dehydrated(false)
                    ->visibleOn('edit'),
                Forms\Components\DateTimePicker::make('last_crawled_at')
                    ->disabled()
                    ->dehydrated(false)
                    ->visibleOn('edit'),
            ])
            ->columns(2);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('name')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('kind')
                    ->badge(),
                Tables\Columns\TextColumn::make('base_url')
                    ->limit(40),
                Tables\Columns\TextColumn::make('organizer_label')
                    ->label('Organizer')
                    ->getStateUsing(function (Source $record): string {
                        $record->loadMissing('organizer.organizable');
                        if (! $record->organizer) {
                            return '—';
                        }
                        $o = $record->organizer;

                        return match ($o->organizable_type) {
                            'Organization' => $o->organizable?->title ?? $o->id,
                            'InitiativeGroup' => $o->organizable?->name ?? $o->id,
                            'Individual' => $o->organizable?->full_name ?? $o->id,
                            default => (string) $o->id,
                        };
                    }),
                Tables\Columns\IconColumn::make('is_active')
                    ->boolean(),
                Tables\Columns\TextColumn::make('last_status')
                    ->badge(),
                Tables\Columns\TextColumn::make('last_crawled_at')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('crawl_period_days'),
                Tables\Columns\TextColumn::make('priority'),
            ])
            ->defaultSort('last_crawled_at', 'desc')
            ->filters([
                Tables\Filters\SelectFilter::make('kind')
                    ->options(array_combine(Source::KINDS, Source::KINDS)),
                Tables\Filters\TernaryFilter::make('is_active'),
                Tables\Filters\SelectFilter::make('last_status')
                    ->options([
                        'pending' => 'Pending',
                        'success' => 'Success',
                        'failed' => 'Failed',
                        'running' => 'Running',
                    ]),
                Tables\Filters\Filter::make('last_crawled_at')
                    ->form([
                        Forms\Components\DatePicker::make('from'),
                        Forms\Components\DatePicker::make('until'),
                    ])
                    ->query(function (Builder $query, array $data): Builder {
                        return $query
                            ->when(
                                $data['from'] ?? null,
                                fn (Builder $q, $date): Builder => $q->whereDate('last_crawled_at', '>=', $date)
                            )
                            ->when(
                                $data['until'] ?? null,
                                fn (Builder $q, $date): Builder => $q->whereDate('last_crawled_at', '<=', $date)
                            );
                    }),
                Tables\Filters\TrashedFilter::make(),
            ])
            ->actions([
                Tables\Actions\EditAction::make(),
            ])
            ->bulkActions([
                Tables\Actions\BulkActionGroup::make([
                    Tables\Actions\DeleteBulkAction::make(),
                    Tables\Actions\ForceDeleteBulkAction::make(),
                    Tables\Actions\RestoreBulkAction::make(),
                ]),
            ]);
    }

    public static function getEloquentQuery(): Builder
    {
        return parent::getEloquentQuery()
            ->withoutGlobalScopes([
                SoftDeletingScope::class,
            ]);
    }

    public static function getRelations(): array
    {
        return [
            RelationManagers\ParseProfilesRelationManager::class,
        ];
    }

    public static function getPages(): array
    {
        return [
            'index' => Pages\ListSources::route('/'),
            'create' => Pages\CreateSource::route('/create'),
            'edit' => Pages\EditSource::route('/{record}/edit'),
        ];
    }
}
