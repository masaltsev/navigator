<?php

namespace App\Filament\Resources;

use App\Filament\Resources\EventInstanceResource\Pages;
use App\Models\EventInstance;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;

class EventInstanceResource extends Resource
{
    protected static ?string $model = EventInstance::class;

    protected static ?string $navigationIcon = 'heroicon-o-clock';

    protected static ?string $navigationGroup = 'Harvester';

    protected static ?int $navigationSort = 41;

    protected static ?string $recordTitleAttribute = 'start_datetime';

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\Select::make('event_id')
                    ->relationship('event', 'title')
                    ->searchable()
                    ->required(),
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

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('event.title')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('start_datetime')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('end_datetime')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('status')
                    ->badge(),
            ])
            ->defaultSort('start_datetime', 'desc')
            ->filters([
                Tables\Filters\SelectFilter::make('status')
                    ->options([
                        'scheduled' => 'Scheduled',
                        'cancelled' => 'Cancelled',
                        'rescheduled' => 'Rescheduled',
                        'finished' => 'Finished',
                    ]),
                Tables\Filters\Filter::make('start_datetime')
                    ->form([
                        Forms\Components\DatePicker::make('from'),
                        Forms\Components\DatePicker::make('until'),
                    ])
                    ->query(function (Builder $query, array $data): Builder {
                        return $query
                            ->when(
                                $data['from'] ?? null,
                                fn (Builder $q, $date): Builder => $q->whereDate('start_datetime', '>=', $date)
                            )
                            ->when(
                                $data['until'] ?? null,
                                fn (Builder $q, $date): Builder => $q->whereDate('start_datetime', '<=', $date)
                            );
                    }),
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
            'index' => Pages\ListEventInstances::route('/'),
            'create' => Pages\CreateEventInstance::route('/create'),
            'edit' => Pages\EditEventInstance::route('/{record}/edit'),
        ];
    }
}
