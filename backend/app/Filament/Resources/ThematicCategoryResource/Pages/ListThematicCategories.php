<?php

namespace App\Filament\Resources\ThematicCategoryResource\Pages;

use App\Filament\Resources\ThematicCategoryResource;
use Filament\Actions;
use Filament\Resources\Pages\ListRecords;

class ListThematicCategories extends ListRecords
{
    protected static string $resource = ThematicCategoryResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
