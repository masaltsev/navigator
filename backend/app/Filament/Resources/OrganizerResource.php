<?php

namespace App\Filament\Resources;

use App\Filament\Resources\OrganizerResource\Pages;
use App\Filament\Resources\OrganizerResource\RelationManagers;
use App\Filament\Support\StatusColors;
use App\Models\Individual;
use App\Models\InitiativeGroup;
use App\Models\Organization;
use App\Models\Organizer;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Forms\Get;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\SoftDeletingScope;
use Illuminate\Support\Facades\DB;

class OrganizerResource extends Resource
{
    protected static ?string $model = Organizer::class;

    protected static ?string $navigationIcon = 'heroicon-o-user-circle';

    protected static ?string $navigationGroup = 'Entities';

    protected static ?int $navigationSort = 22;

    protected static ?string $recordTitleAttribute = 'id';

    public static function canGloballySearch(): bool
    {
        return false;
    }

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\Select::make('organizable_type')
                    ->label('Organizer type')
                    ->options([
                        'Organization' => 'Organization',
                        'InitiativeGroup' => 'Initiative group',
                        'Individual' => 'Individual',
                    ])
                    ->required()
                    ->live()
                    ->disabledOn('edit'),
                Forms\Components\Select::make('organizable_id')
                    ->label('Linked record')
                    ->options(function (Get $get): array {
                        return match ($get('organizable_type')) {
                            'Organization' => Organization::query()->orderBy('title')->pluck('title', 'id')->all(),
                            'InitiativeGroup' => InitiativeGroup::query()->orderBy('name')->pluck('name', 'id')->all(),
                            'Individual' => Individual::query()->orderBy('full_name')->pluck('full_name', 'id')->all(),
                            default => [],
                        };
                    })
                    ->searchable()
                    ->required()
                    ->disabledOn('edit'),
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
            ]);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('organizable_type')
                    ->badge(),
                Tables\Columns\TextColumn::make('organizable_label')
                    ->label('Name')
                    ->getStateUsing(function (Organizer $record): string {
                        $record->loadMissing('organizable');
                        if (! $record->organizable) {
                            return '—';
                        }

                        return match ($record->organizable_type) {
                            'Organization' => $record->organizable->title,
                            'InitiativeGroup' => $record->organizable->name,
                            'Individual' => $record->organizable->full_name,
                            default => (string) $record->id,
                        };
                    })
                    ->searchable(query: function (Builder $query, string $search): Builder {
                        $op = DB::connection()->getDriverName() === 'pgsql' ? 'ilike' : 'like';
                        $term = '%'.$search.'%';

                        return $query
                            ->whereHasMorph(
                                'organizable',
                                [Organization::class, InitiativeGroup::class, Individual::class],
                                function (Builder $query, string $type) use ($op, $term): void {
                                    match ($type) {
                                        Organization::class => $query->where('title', $op, $term),
                                        InitiativeGroup::class => $query->where('name', $op, $term),
                                        Individual::class => $query->where('full_name', $op, $term),
                                        default => null,
                                    };
                                }
                            );
                    }),
                Tables\Columns\TextColumn::make('status')
                    ->badge()
                    ->color(fn (?string $state): string => StatusColors::badgeColor($state)),
                Tables\Columns\TextColumn::make('sources_count')
                    ->counts('sources')
                    ->label('Sources'),
                Tables\Columns\TextColumn::make('events_count')
                    ->counts('events')
                    ->label('Events'),
                Tables\Columns\TextColumn::make('created_at')
                    ->dateTime()
                    ->sortable(),
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
                Tables\Filters\SelectFilter::make('organizable_type')
                    ->options([
                        'Organization' => 'Organization',
                        'InitiativeGroup' => 'Initiative group',
                        'Individual' => 'Individual',
                    ]),
                Tables\Filters\TrashedFilter::make(),
            ])
            ->actions([
                Tables\Actions\Action::make('approve')
                    ->icon('heroicon-o-check-circle')
                    ->color('success')
                    ->visible(fn (Organizer $record): bool => $record->status !== 'approved')
                    ->action(fn (Organizer $record) => $record->update(['status' => 'approved'])),
                Tables\Actions\Action::make('reject')
                    ->icon('heroicon-o-x-circle')
                    ->color('danger')
                    ->visible(fn (Organizer $record): bool => $record->status !== 'rejected')
                    ->action(fn (Organizer $record) => $record->update(['status' => 'rejected'])),
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
            RelationManagers\SourcesRelationManager::class,
            RelationManagers\EventsRelationManager::class,
            RelationManagers\UsersRelationManager::class,
        ];
    }

    public static function getPages(): array
    {
        return [
            'index' => Pages\ListOrganizers::route('/'),
            'create' => Pages\CreateOrganizer::route('/create'),
            'edit' => Pages\EditOrganizer::route('/{record}/edit'),
        ];
    }
}
