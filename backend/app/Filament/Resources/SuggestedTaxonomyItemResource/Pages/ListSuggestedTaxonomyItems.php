<?php

namespace App\Filament\Resources\SuggestedTaxonomyItemResource\Pages;

use App\Filament\Resources\SuggestedTaxonomyItemResource;
use Filament\Actions;
use Filament\Resources\Pages\ListRecords;

class ListSuggestedTaxonomyItems extends ListRecords
{
    protected static string $resource = SuggestedTaxonomyItemResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
