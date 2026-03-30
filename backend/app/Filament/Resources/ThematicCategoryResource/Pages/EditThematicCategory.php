<?php

namespace App\Filament\Resources\ThematicCategoryResource\Pages;

use App\Filament\Resources\ThematicCategoryResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditThematicCategory extends EditRecord
{
    protected static string $resource = ThematicCategoryResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
