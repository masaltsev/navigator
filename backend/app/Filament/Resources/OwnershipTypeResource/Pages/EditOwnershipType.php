<?php

namespace App\Filament\Resources\OwnershipTypeResource\Pages;

use App\Filament\Resources\OwnershipTypeResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditOwnershipType extends EditRecord
{
    protected static string $resource = OwnershipTypeResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
