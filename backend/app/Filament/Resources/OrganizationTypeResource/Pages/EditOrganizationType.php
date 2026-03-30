<?php

namespace App\Filament\Resources\OrganizationTypeResource\Pages;

use App\Filament\Resources\OrganizationTypeResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditOrganizationType extends EditRecord
{
    protected static string $resource = OrganizationTypeResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
