<?php

namespace App\Filament\Resources\SuggestedTaxonomyItemResource\Pages;

use App\Filament\Resources\SuggestedTaxonomyItemResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditSuggestedTaxonomyItem extends EditRecord
{
    protected static string $resource = SuggestedTaxonomyItemResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
