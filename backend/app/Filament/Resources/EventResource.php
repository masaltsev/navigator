<?php

namespace App\Filament\Resources;

use App\Filament\Resources\EventResource\Pages;
use App\Filament\Resources\EventResource\RelationManagers;
use App\Filament\Support\StatusColors;
use App\Models\Event;
use App\Models\Organizer;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Forms\Get;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\SoftDeletingScope;

class EventResource extends Resource
{
    protected static ?string $model = Event::class;

    protected static ?string $navigationIcon = 'heroicon-o-calendar-days';

    protected static ?string $navigationGroup = 'Entities';

    protected static ?int $navigationSort = 21;

    protected static ?string $recordTitleAttribute = 'title';

    /**
     * @return array<int, string>
     */
    public static function getGloballySearchableAttributes(): array
    {
        return ['title', 'description'];
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
                        Forms\Components\RichEditor::make('description')
                            ->columnSpanFull(),
                        Forms\Components\Select::make('attendance_mode')
                            ->options([
                                'offline' => 'Offline',
                                'online' => 'Online',
                                'mixed' => 'Mixed',
                            ])
                            ->required()
                            ->native(false),
                        Forms\Components\TextInput::make('online_url')
                            ->url()
                            ->maxLength(255)
                            ->visible(fn (Get $get): bool => in_array($get('attendance_mode'), ['online', 'mixed'], true)),
                        Forms\Components\TextInput::make('rrule_string')
                            ->maxLength(255),
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
                        Forms\Components\TextInput::make('event_page_url')
                            ->maxLength(255)
                            ->url(),
                        Forms\Components\TextInput::make('source_reference')
                            ->maxLength(255),
                    ])
                    ->columns(2),
                Forms\Components\Section::make('Linking')
                    ->schema([
                        Forms\Components\Select::make('organizer_id')
                            ->label('Organizer')
                            ->options(function (): array {
                                return Organizer::query()
                                    ->with('organizable')
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
                            ->searchable()
                            ->required(),
                        Forms\Components\Select::make('organization_id')
                            ->relationship('organization', 'title')
                            ->searchable()
                            ->preload(),
                        Forms\Components\CheckboxList::make('categories')
                            ->relationship('categories', 'name')
                            ->columns(2)
                            ->searchable(),
                        Forms\Components\TagsInput::make('target_audience')
                            ->placeholder('Audience tag'),
                    ])
                    ->columns(2),
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
                    ])
                    ->columns(2)
                    ->collapsed()
                    ->collapsible(),
            ]);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('title')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('organizer_label')
                    ->label('Organizer')
                    ->getStateUsing(function (Event $record): string {
                        $o = $record->organizer;
                        if (! $o || ! $o->organizable) {
                            return '—';
                        }

                        return match ($o->organizable_type) {
                            'Organization' => $o->organizable->title,
                            'InitiativeGroup' => $o->organizable->name,
                            'Individual' => $o->organizable->full_name,
                            default => (string) $o->id,
                        };
                    }),
                Tables\Columns\TextColumn::make('status')
                    ->badge()
                    ->color(fn (?string $state): string => StatusColors::badgeColor($state)),
                Tables\Columns\TextColumn::make('attendance_mode'),
                Tables\Columns\TextColumn::make('organization.title')
                    ->label('Organization')
                    ->toggleable(),
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
                Tables\Filters\SelectFilter::make('attendance_mode')
                    ->options([
                        'offline' => 'Offline',
                        'online' => 'Online',
                        'mixed' => 'Mixed',
                    ]),
                Tables\Filters\SelectFilter::make('categories')
                    ->relationship('categories', 'name')
                    ->multiple()
                    ->label('Category'),
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
                Tables\Filters\SelectFilter::make('organizer_id')
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
                Tables\Filters\TrashedFilter::make(),
            ])
            ->actions([
                Tables\Actions\Action::make('approve')
                    ->icon('heroicon-o-check-circle')
                    ->color('success')
                    ->visible(fn (Event $record): bool => $record->status !== 'approved')
                    ->action(fn (Event $record) => $record->update(['status' => 'approved'])),
                Tables\Actions\Action::make('reject')
                    ->icon('heroicon-o-x-circle')
                    ->color('danger')
                    ->visible(fn (Event $record): bool => $record->status !== 'rejected')
                    ->action(fn (Event $record) => $record->update(['status' => 'rejected'])),
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
            RelationManagers\EventInstancesRelationManager::class,
            RelationManagers\VenuesRelationManager::class,
        ];
    }

    public static function getPages(): array
    {
        return [
            'index' => Pages\ListEvents::route('/'),
            'create' => Pages\CreateEvent::route('/create'),
            'edit' => Pages\EditEvent::route('/{record}/edit'),
        ];
    }
}
