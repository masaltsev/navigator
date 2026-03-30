<?php

namespace App\Filament\Resources\OrganizationTypeResource\Pages;

use App\Filament\Resources\OrganizationTypeResource;
use Filament\Actions;
use Filament\Resources\Pages\ListRecords;

class ListOrganizationTypes extends ListRecords
{
    protected static string $resource = OrganizationTypeResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
