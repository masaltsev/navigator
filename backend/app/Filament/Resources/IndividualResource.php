<?php

namespace App\Filament\Resources;

use App\Filament\Resources\IndividualResource\Pages;
use App\Models\Individual;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\SoftDeletingScope;

class IndividualResource extends Resource
{
    protected static ?string $model = Individual::class;

    protected static ?string $navigationIcon = 'heroicon-o-user';

    protected static ?string $navigationGroup = 'Entities';

    protected static ?int $navigationSort = 24;

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\TextInput::make('full_name')
                    ->required()
                    ->maxLength(255),
                Forms\Components\TextInput::make('role')
                    ->maxLength(255),
                Forms\Components\TextInput::make('contact_email')
                    ->email()
                    ->maxLength(255),
                Forms\Components\TextInput::make('contact_phone')
                    ->maxLength(255),
                Forms\Components\Toggle::make('consent_given')
                    ->default(false),
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
            ]);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('full_name')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('role'),
                Tables\Columns\TextColumn::make('contact_email')
                    ->searchable(),
                Tables\Columns\IconColumn::make('consent_given')
                    ->boolean(),
                Tables\Columns\IconColumn::make('has_organizer')
                    ->label('Organizer')
                    ->getStateUsing(fn (Individual $r): bool => $r->organizer()->exists()),
                Tables\Columns\TextColumn::make('created_at')
                    ->dateTime()
                    ->sortable(),
            ])
            ->defaultSort('full_name')
            ->filters([
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
            'index' => Pages\ListIndividuals::route('/'),
            'create' => Pages\CreateIndividual::route('/create'),
            'edit' => Pages\EditIndividual::route('/{record}/edit'),
        ];
    }
}
