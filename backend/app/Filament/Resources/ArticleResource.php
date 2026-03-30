<?php

namespace App\Filament\Resources;

use App\Filament\Resources\ArticleResource\Pages;
use App\Filament\Support\StatusColors;
use App\Models\Article;
use App\Models\Service;
use App\Models\ThematicCategory;
use App\Support\Content\HtmlToMarkdownConverter;
use App\Support\HierarchicalDictionaryOptions;
use App\Support\Strings\SlugifyUnicode;
use Filament\Forms;
use Filament\Forms\Form;
use Filament\Forms\Get;
use Filament\Forms\Set;
use Filament\Resources\Resource;
use Filament\Tables;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\SoftDeletingScope;

class ArticleResource extends Resource
{
    protected static ?string $model = Article::class;

    protected static ?string $navigationIcon = 'heroicon-o-document-text';

    protected static ?string $navigationGroup = 'Content';

    protected static ?int $navigationSort = 30;

    protected static ?string $recordTitleAttribute = 'title';

    /**
     * @return array<int, string>
     */
    public static function getGloballySearchableAttributes(): array
    {
        return ['title', 'slug', 'content'];
    }

    public static function form(Form $form): Form
    {
        return $form
            ->schema([
                Forms\Components\Section::make('Content')
                    ->schema([
                        Forms\Components\TextInput::make('title')
                            ->required()
                            ->maxLength(255)
                            ->live(onBlur: true)
                            ->afterStateUpdated(function (Set $set, Get $get, ?string $state): void {
                                if (filled($get('slug')) || ! filled($state)) {
                                    return;
                                }
                                $set('slug', SlugifyUnicode::slugifyUnicodePreserveCyrillic((string) $state));
                            }),
                        Forms\Components\TextInput::make('slug')
                            ->required()
                            ->maxLength(255)
                            ->unique(Article::class, 'slug', ignoreRecord: true),
                        Forms\Components\MarkdownEditor::make('content')
                            ->columnSpanFull()
                            ->afterStateHydrated(function (Forms\Components\MarkdownEditor $component, ?string $state): void {
                                if ($state !== null && HtmlToMarkdownConverter::looksLikeHtml($state)) {
                                    $component->state(HtmlToMarkdownConverter::convert($state));
                                }
                            })
                            ->toolbarButtons([
                                'attachFiles',
                                'blockquote',
                                'bold',
                                'bulletList',
                                'codeBlock',
                                'heading',
                                'italic',
                                'link',
                                'orderedList',
                                'redo',
                                'strike',
                                'table',
                                'undo',
                            ]),
                        Forms\Components\Textarea::make('excerpt')
                            ->columnSpanFull(),
                        Forms\Components\TextInput::make('content_url')
                            ->url()
                            ->maxLength(65535),
                        Forms\Components\TextInput::make('featured_image_url')
                            ->maxLength(255)
                            ->url(),
                    ]),
                Forms\Components\Section::make('Linking')
                    ->schema([
                        Forms\Components\Select::make('organization_id')
                            ->relationship('organization', 'title')
                            ->searchable()
                            ->preload(),
                        Forms\Components\CheckboxList::make('thematicCategories')
                            ->relationship('thematicCategories', 'name')
                            ->options(fn () => HierarchicalDictionaryOptions::options(ThematicCategory::class))
                            ->columns(2)
                            ->gridDirection('row')
                            ->searchable()
                            ->label('Thematic categories'),
                        Forms\Components\CheckboxList::make('services')
                            ->relationship('services', 'name')
                            ->options(fn () => HierarchicalDictionaryOptions::options(Service::class))
                            ->columns(2)
                            ->gridDirection('row')
                            ->searchable()
                            ->label('Services'),
                        Forms\Components\CheckboxList::make('specialistProfiles')
                            ->relationship('specialistProfiles', 'name')
                            ->columns(2)
                            ->gridDirection('row')
                            ->searchable()
                            ->label('Specialist profiles'),
                        Forms\Components\Select::make('status')
                            ->options([
                                'draft' => 'Draft',
                                'published' => 'Published',
                                'archived' => 'Archived',
                            ])
                            ->required()
                            ->native(false),
                        Forms\Components\DateTimePicker::make('published_at')
                            ->seconds(false),
                    ])
                    ->columns(2),
            ]);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->columns([
                Tables\Columns\TextColumn::make('title')
                    ->searchable()
                    ->sortable(),
                Tables\Columns\TextColumn::make('slug')
                    ->searchable(),
                Tables\Columns\TextColumn::make('status')
                    ->badge()
                    ->color(fn (?string $state): string => StatusColors::badgeColor($state)),
                Tables\Columns\TextColumn::make('organization.title')
                    ->label('Organization')
                    ->toggleable(),
                Tables\Columns\TextColumn::make('thematicCategories.name')
                    ->label('Categories')
                    ->badge()
                    ->toggleable(isToggledHiddenByDefault: true),
                Tables\Columns\TextColumn::make('published_at')
                    ->dateTime()
                    ->sortable(),
                Tables\Columns\TextColumn::make('created_at')
                    ->dateTime()
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                Tables\Filters\SelectFilter::make('status')
                    ->options([
                        'draft' => 'Draft',
                        'published' => 'Published',
                        'archived' => 'Archived',
                    ]),
                Tables\Filters\SelectFilter::make('thematicCategories')
                    ->relationship('thematicCategories', 'name')
                    ->multiple()
                    ->label('Thematic category'),
                Tables\Filters\SelectFilter::make('services')
                    ->relationship('services', 'name')
                    ->multiple()
                    ->label('Service'),
                Tables\Filters\SelectFilter::make('organization_id')
                    ->relationship('organization', 'title')
                    ->searchable(),
                Tables\Filters\Filter::make('published_at')
                    ->form([
                        Forms\Components\DatePicker::make('from'),
                        Forms\Components\DatePicker::make('until'),
                    ])
                    ->query(function (Builder $query, array $data): Builder {
                        return $query
                            ->when(
                                $data['from'] ?? null,
                                fn (Builder $q, $date): Builder => $q->whereDate('published_at', '>=', $date)
                            )
                            ->when(
                                $data['until'] ?? null,
                                fn (Builder $q, $date): Builder => $q->whereDate('published_at', '<=', $date)
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
        return [];
    }

    public static function getPages(): array
    {
        return [
            'index' => Pages\ListArticles::route('/'),
            'create' => Pages\CreateArticle::route('/create'),
            'edit' => Pages\EditArticle::route('/{record}/edit'),
        ];
    }
}
