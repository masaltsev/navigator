<?php

namespace App\Filament\Resources;

use App\Filament\Resources\OrganizationResource\Pages;
use App\Filament\Resources\OrganizationResource\RelationManagers;
use App\Filament\Support\StatusColors;
use App\Models\Organization;
use App\Models\Service;
use App\Models\ThematicCategory;
use App\Support\HierarchicalDictionaryOptions;
use Filament\Forms;
use Filament\Forms\Components\Component;
use Filament\Forms\Form;
use Filament\Forms\Get;
use Filament\Resources\Pages\EditRecord;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\SoftDeletingScope;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\HtmlString;

class OrganizationResource extends Resource
{
    protected static ?string $model = Organization::class;

    protected static ?string $navigationIcon = 'heroicon-o-building-office';

    protected static ?string $navigationGroup = 'Entities';

    protected static ?int $navigationSort = 20;

    protected static ?string $recordTitleAttribute = 'title';

    /**
     * @return array<int, string>
     */
    public static function getGloballySearchableAttributes(): array
    {
        // Exclude description: large HTML bodies would blow memory if global search loads many rows.
        return ['title', 'short_title', 'inn', 'ogrn'];
    }

    /**
     * Filament BelongsToMany CheckboxList uses DISTINCT + select(table.*); PostgreSQL cannot DISTINCT rows
     * that include json columns (e.g. keywords on organization_types / thematic_categories).
     */
    protected static function narrowRelationshipOptionsQuery(Builder $query): void
    {
        $table = $query->getModel()->getTable();
        $query->getQuery()->distinct = false;
        $query->select("{$table}.id", "{$table}.name");
    }

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\Section::make('Basic info')
                    ->schema([
                        Forms\Components\TextInput::make('title')
                            ->required()
                            ->maxLength(255),
                        Forms\Components\TextInput::make('short_title')
                            ->maxLength(100),
                        Forms\Components\RichEditor::make('description')
                            ->columnSpanFull(),
                        Forms\Components\TextInput::make('inn')
                            ->maxLength(255)
                            ->unique(Organization::class, 'inn', ignoreRecord: true),
                        Forms\Components\TextInput::make('ogrn')
                            ->maxLength(255)
                            ->unique(Organization::class, 'ogrn', ignoreRecord: true),
                        Forms\Components\TagsInput::make('site_urls')
                            ->placeholder('Add URL'),
                        Forms\Components\Select::make('status')
                            ->options([
                                'approved' => 'Approved',
                                'in_review' => 'In review',
                                'rejected' => 'Rejected',
                                'draft' => 'Draft',
                                'pending' => 'Pending',
                            ])
                            ->required()
                            ->native(false),
                        Forms\Components\TextInput::make('source_reference')
                            ->maxLength(255),
                        Forms\Components\Placeholder::make('inn_duplicate_hint')
                            ->content(function (Get $get, Component $component): HtmlString|string {
                                $inn = trim((string) $get('inn'));
                                if ($inn === '') {
                                    return '';
                                }
                                $livewire = $component->getLivewire();
                                $query = Organization::query()->where('inn', $inn);
                                if ($livewire instanceof EditRecord) {
                                    $query->whereKeyNot($livewire->getRecord()->getKey());
                                }
                                $dup = $query->first();
                                if (! $dup) {
                                    return '';
                                }
                                $url = self::getUrl('edit', ['record' => $dup]);

                                return new HtmlString(
                                    'Organization with this INN exists: <a class="text-primary-600 underline" href="'
                                    .e($url).'">'.e($dup->title).'</a>'
                                );
                            })
                            ->columnSpanFull()
                            ->visible(fn (Get $get): bool => filled(trim((string) $get('inn')))),
                        Forms\Components\Placeholder::make('ogrn_duplicate_hint')
                            ->content(function (Get $get, Component $component): HtmlString|string {
                                $ogrn = trim((string) $get('ogrn'));
                                if ($ogrn === '') {
                                    return '';
                                }
                                $livewire = $component->getLivewire();
                                $query = Organization::query()->where('ogrn', $ogrn);
                                if ($livewire instanceof EditRecord) {
                                    $query->whereKeyNot($livewire->getRecord()->getKey());
                                }
                                $dup = $query->first();
                                if (! $dup) {
                                    return '';
                                }
                                $url = self::getUrl('edit', ['record' => $dup]);

                                return new HtmlString(
                                    'Organization with this OGRN exists: <a class="text-primary-600 underline" href="'
                                    .e($url).'">'.e($dup->title).'</a>'
                                );
                            })
                            ->columnSpanFull()
                            ->visible(fn (Get $get): bool => filled(trim((string) $get('ogrn')))),
                    ])
                    ->columns(2),
                Forms\Components\Section::make('Classification')
                    ->schema([
                        Forms\Components\Select::make('ownership_type_id')
                            ->relationship('ownershipType', 'name')
                            ->searchable()
                            ->preload(),
                        Forms\Components\Select::make('coverage_level_id')
                            ->relationship('coverageLevel', 'name')
                            ->searchable()
                            ->preload(),
                        Forms\Components\CheckboxList::make('organizationTypes')
                            ->relationship(
                                'organizationTypes',
                                'name',
                                fn (Builder $query) => self::narrowRelationshipOptionsQuery($query),
                            )
                            ->columns(2)
                            ->gridDirection('row')
                            ->searchable(),
                        Forms\Components\CheckboxList::make('thematicCategories')
                            ->relationship('thematicCategories', 'name')
                            ->options(fn () => HierarchicalDictionaryOptions::options(ThematicCategory::class))
                            ->columns(2)
                            ->gridDirection('row')
                            ->searchable(),
                        Forms\Components\Select::make('services')
                            ->relationship(
                                'services',
                                'name',
                                fn (Builder $query) => self::narrowRelationshipOptionsQuery($query),
                            )
                            ->options(fn () => HierarchicalDictionaryOptions::options(Service::class))
                            ->multiple()
                            ->searchable()
                            ->preload(),
                        Forms\Components\Select::make('specialistProfiles')
                            ->relationship(
                                'specialistProfiles',
                                'name',
                                fn (Builder $query) => self::narrowRelationshipOptionsQuery($query),
                            )
                            ->multiple()
                            ->searchable()
                            ->preload(),
                        Forms\Components\TagsInput::make('target_audience')
                            ->placeholder('Audience tag'),
                        Forms\Components\Toggle::make('works_with_elderly')
                            ->default(false),
                    ])
                    ->columns(2),
                Forms\Components\Section::make('Social')
                    ->schema([
                        Forms\Components\TextInput::make('vk_group_id')
                            ->numeric(),
                        Forms\Components\TextInput::make('ok_group_id')
                            ->numeric(),
                    ])
                    ->columns(2),
                Forms\Components\Section::make('Organizer')
                    ->relationship('organizer')
                    ->schema([
                        Forms\Components\Select::make('status')
                            ->options([
                                'approved' => 'Approved',
                                'in_review' => 'In review',
                                'rejected' => 'Rejected',
                                'draft' => 'Draft',
                                'pending' => 'Pending',
                            ])
                            ->required()
                            ->native(false),
                        Forms\Components\TagsInput::make('contact_phones')
                            ->placeholder('Phone'),
                        Forms\Components\TagsInput::make('contact_emails')
                            ->placeholder('Email'),
                    ])
                    ->columns(2)
                    ->collapsible(),
                Forms\Components\Section::make('AI pipeline')
                    ->schema([
                        Forms\Components\TextInput::make('ai_confidence_score')
                            ->numeric()
                            ->disabled()
                            ->dehydrated(false),
                        Forms\Components\Textarea::make('ai_explanation')
                            ->disabled()
                            ->dehydrated(false)
                            ->columnSpanFull(),
                        Forms\Components\Textarea::make('ai_source_trace')
                            ->label('AI source trace (JSON)')
                            ->formatStateUsing(fn ($state): string => is_array($state) ? (string) json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE) : (string) $state)
                            ->disabled()
                            ->dehydrated(false)
                            ->columnSpanFull(),
                        Forms\Components\Textarea::make('verified_fields')
                            ->label('Verified fields (JSON)')
                            ->formatStateUsing(fn ($state): string => is_array($state) ? (string) json_encode($state, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE) : (string) $state)
                            ->disabled()
                            ->dehydrated(false)
                            ->columnSpanFull(),
                        Forms\Components\TextInput::make('content_hash')
                            ->maxLength(32)
                            ->disabled()
                            ->dehydrated(false),
                    ])
                    ->columns(2)
                    ->collapsed()
                    ->collapsible(),
            ]);
    }

    public static function table(Table $table): Table
    {
        return $table
            // Avoid loading huge text/json columns on the list (especially when users pick "All" rows).
            ->modifyQueryUsing(fn (Builder $query): Builder => $query->select([
                'organizations.id',
                'organizations.title',
                'organizations.short_title',
                'organizations.inn',
                'organizations.ogrn',
                'organizations.status',
                'organizations.ownership_type_id',
                'organizations.works_with_elderly',
                'organizations.ai_confidence_score',
                'organizations.created_at',
                'organizations.updated_at',
                'organizations.deleted_at',
            ]))
            // Default Filament options include "all", which OOMs on large tables.
            ->paginationPageOptions([10, 25, 50, 100])
            ->columns([
                Tables\Columns\TextColumn::make('title')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('short_title')
                    ->searchable()
                    ->toggleable(),
                Tables\Columns\TextColumn::make('inn')
                    ->searchable(),
                Tables\Columns\TextColumn::make('ogrn')
                    ->searchable(),
                Tables\Columns\TextColumn::make('status')
                    ->badge()
                    ->color(fn (?string $state): string => StatusColors::badgeColor($state)),
                Tables\Columns\TextColumn::make('ownershipType.name')
                    ->label('Ownership')
                    ->sortable(),
                Tables\Columns\IconColumn::make('works_with_elderly')
                    ->boolean(),
                Tables\Columns\TextColumn::make('ai_confidence_score')
                    ->numeric(decimalPlaces: 4)
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true),
                Tables\Columns\TextColumn::make('created_at')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('updated_at')
                    ->dateTime()
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true),
                Tables\Columns\TextColumn::make('deleted_at')
                    ->dateTime()
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                Tables\Filters\SelectFilter::make('status')
                    ->options([
                        'approved' => 'Approved',
                        'in_review' => 'In review',
                        'rejected' => 'Rejected',
                        'draft' => 'Draft',
                        'pending' => 'Pending',
                    ]),
                Tables\Filters\SelectFilter::make('ownership_type_id')
                    ->relationship('ownershipType', 'name')
                    ->label('Ownership type'),
                Tables\Filters\SelectFilter::make('coverage_level_id')
                    ->relationship('coverageLevel', 'name')
                    ->label('Coverage level'),
                Tables\Filters\SelectFilter::make('organizationTypes')
                    ->relationship('organizationTypes', 'name')
                    ->multiple()
                    ->label('Organization type'),
                Tables\Filters\SelectFilter::make('thematicCategories')
                    ->relationship('thematicCategories', 'name')
                    ->multiple()
                    ->label('Thematic category'),
                Tables\Filters\SelectFilter::make('services')
                    ->relationship('services', 'name')
                    ->multiple(),
                Tables\Filters\SelectFilter::make('specialistProfiles')
                    ->relationship('specialistProfiles', 'name')
                    ->multiple(),
                Tables\Filters\TernaryFilter::make('works_with_elderly'),
                Tables\Filters\Filter::make('created_at')
                    ->form([
                        Forms\Components\DatePicker::make('from'),
                        Forms\Components\DatePicker::make('until'),
                    ])
                    ->query(function (Builder $query, array $data): Builder {
                        return $query
                            ->when(
                                $data['from'] ?? null,
                                fn (Builder $q, $date): Builder => $q->whereDate('created_at', '>=', $date)
                            )
                            ->when(
                                $data['until'] ?? null,
                                fn (Builder $q, $date): Builder => $q->whereDate('created_at', '<=', $date)
                            );
                    }),
                Tables\Filters\Filter::make('venue_region')
                    ->form([
                        Forms\Components\TextInput::make('region_iso')
                            ->label('Venue region ISO'),
                        Forms\Components\TextInput::make('region_code')
                            ->label('Venue region code'),
                    ])
                    ->query(function (Builder $query, array $data): Builder {
                        if (! Schema::hasTable('venues')) {
                            return $query;
                        }

                        return $query->when(
                            filled($data['region_iso'] ?? null) || filled($data['region_code'] ?? null),
                            fn (Builder $q): Builder => $q->whereHas('venues', function (Builder $vq) use ($data): void {
                                if (filled($data['region_iso'] ?? null)) {
                                    $vq->where('region_iso', $data['region_iso']);
                                }
                                if (filled($data['region_code'] ?? null)) {
                                    $vq->where('region_code', $data['region_code']);
                                }
                            })
                        );
                    }),
                Tables\Filters\TrashedFilter::make(),
            ])
            ->actions([
                Tables\Actions\Action::make('approve')
                    ->icon('heroicon-o-check-circle')
                    ->color('success')
                    ->visible(fn (Organization $record): bool => $record->status !== 'approved')
                    ->action(fn (Organization $record) => $record->update(['status' => 'approved'])),
                Tables\Actions\Action::make('reject')
                    ->icon('heroicon-o-x-circle')
                    ->color('danger')
                    ->visible(fn (Organization $record): bool => $record->status !== 'rejected')
                    ->action(fn (Organization $record) => $record->update(['status' => 'rejected'])),
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
            RelationManagers\VenuesRelationManager::class,
            RelationManagers\EventsRelationManager::class,
            RelationManagers\ArticlesRelationManager::class,
            RelationManagers\SuggestedTaxonomyItemsRelationManager::class,
        ];
    }

    public static function getPages(): array
    {
        return [
            'index' => Pages\ListOrganizations::route('/'),
            'create' => Pages\CreateOrganization::route('/create'),
            'edit' => Pages\EditOrganization::route('/{record}/edit'),
        ];
    }
}
