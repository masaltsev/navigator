<?php

namespace App\Filament\Resources\InitiativeGroupResource\Pages;

use App\Filament\Resources\InitiativeGroupResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditInitiativeGroup extends EditRecord
{
    protected static string $resource = InitiativeGroupResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
