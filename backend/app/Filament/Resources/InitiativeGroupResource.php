<?php

namespace App\Filament\Resources;

use App\Filament\Resources\InitiativeGroupResource\Pages;
use App\Filament\Support\StatusColors;
use App\Models\InitiativeGroup;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\SoftDeletingScope;

class InitiativeGroupResource extends Resource
{
    protected static ?string $model = InitiativeGroup::class;

    protected static ?string $navigationIcon = 'heroicon-o-user-group';

    protected static ?string $navigationGroup = 'Entities';

    protected static ?int $navigationSort = 25;

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\TextInput::make('name')
                    ->required()
                    ->maxLength(255),
                Forms\Components\Textarea::make('description')
                    ->columnSpanFull(),
                Forms\Components\TextInput::make('community_focus')
                    ->maxLength(255),
                Forms\Components\DatePicker::make('established_date'),
                Forms\Components\Toggle::make('works_with_elderly')
                    ->default(false),
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
                Forms\Components\TagsInput::make('target_audience')
                    ->placeholder('Audience tag'),
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
                        Forms\Components\TagsInput::make('contact_phones'),
                        Forms\Components\TagsInput::make('contact_emails'),
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
                Tables\Columns\TextColumn::make('name')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('status')
                    ->badge()
                    ->color(fn (?string $state): string => StatusColors::badgeColor($state)),
                Tables\Columns\TextColumn::make('community_focus'),
                Tables\Columns\IconColumn::make('works_with_elderly')
                    ->boolean(),
                Tables\Columns\TextColumn::make('established_date')
                    ->date(),
                Tables\Columns\TextColumn::make('created_at')
                    ->dateTime()
                    ->sortable(),
            ])
            ->defaultSort('name')
            ->filters([
                Tables\Filters\SelectFilter::make('status')
                    ->options([
                        'approved' => 'Approved',
                        'in_review' => 'In review',
                        'rejected' => 'Rejected',
                        'draft' => 'Draft',
                        'pending' => 'Pending',
                    ]),
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
        return [];
    }

    public static function getPages(): array
    {
        return [
            'index' => Pages\ListInitiativeGroups::route('/'),
            'create' => Pages\CreateInitiativeGroup::route('/create'),
            'edit' => Pages\EditInitiativeGroup::route('/{record}/edit'),
        ];
    }
}
