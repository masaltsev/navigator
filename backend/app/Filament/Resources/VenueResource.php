<?php

namespace App\Filament\Resources;

use App\Filament\Resources\VenueResource\Pages;
use App\Filament\Resources\VenueResource\RelationManagers;
use App\Models\Venue;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\SoftDeletingScope;

class VenueResource extends Resource
{
    protected static ?string $model = Venue::class;

    protected static ?string $navigationIcon = 'heroicon-o-map-pin';

    protected static ?string $navigationGroup = 'Entities';

    protected static ?int $navigationSort = 23;

    protected static ?string $recordTitleAttribute = 'address_raw';

    /**
     * @return array<int, string>
     */
    public static function getGloballySearchableAttributes(): array
    {
        return ['address_raw', 'fias_id'];
    }

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\TextInput::make('address_raw')
                    ->required()
                    ->maxLength(255),
                Forms\Components\TextInput::make('fias_id')
                    ->maxLength(255),
                Forms\Components\TextInput::make('kladr_id')
                    ->maxLength(255),
                Forms\Components\TextInput::make('fias_level')
                    ->maxLength(10),
                Forms\Components\TextInput::make('city_fias_id')
                    ->maxLength(36),
                Forms\Components\TextInput::make('region_iso')
                    ->maxLength(255),
                Forms\Components\TextInput::make('region_code')
                    ->maxLength(255),
                Forms\Components\TextInput::make('latitude')
                    ->label('Latitude')
                    ->numeric()
                    ->helperText('WGS84 decimal degrees'),
                Forms\Components\TextInput::make('longitude')
                    ->label('Longitude')
                    ->numeric()
                    ->helperText('WGS84 decimal degrees'),
            ])
            ->columns(2);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('address_raw')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('region_iso')
                    ->sortable(),
                Tables\Columns\TextColumn::make('region_code')
                    ->toggleable(),
                Tables\Columns\TextColumn::make('fias_id')
                    ->toggleable(isToggledHiddenByDefault: true),
                Tables\Columns\TextColumn::make('coords')
                    ->label('Coords')
                    ->getStateUsing(function (Venue $record): string {
                        $c = $record->coordinates_array;

                        return $c ? $c['lat'].', '.$c['lng'] : '—';
                    }),
                Tables\Columns\TextColumn::make('organizations_count')
                    ->counts('organizations')
                    ->label('Orgs'),
                Tables\Columns\TextColumn::make('events_count')
                    ->counts('events')
                    ->label('Events'),
                Tables\Columns\TextColumn::make('created_at')
                    ->dateTime()
                    ->sortable(),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                Tables\Filters\Filter::make('has_coordinates')
                    ->label('Has coordinates')
                    ->query(fn (Builder $query): Builder => $query->whereNotNull('coordinates')),
                Tables\Filters\SelectFilter::make('region_iso')
                    ->options(fn (): array => Venue::query()->whereNotNull('region_iso')->distinct()->orderBy('region_iso')->pluck('region_iso', 'region_iso')->all()),
                Tables\Filters\SelectFilter::make('region_code')
                    ->options(fn (): array => Venue::query()->whereNotNull('region_code')->distinct()->orderBy('region_code')->pluck('region_code', 'region_code')->all()),
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
            RelationManagers\OrganizationsRelationManager::class,
            RelationManagers\EventsRelationManager::class,
        ];
    }

    public static function getPages(): array
    {
        return [
            'index' => Pages\ListVenues::route('/'),
            'create' => Pages\CreateVenue::route('/create'),
            'edit' => Pages\EditVenue::route('/{record}/edit'),
        ];
    }
}
