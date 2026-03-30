<?php

namespace App\Filament\Resources\OwnershipTypeResource\Pages;

use App\Filament\Resources\OwnershipTypeResource;
use Filament\Actions;
use Filament\Resources\Pages\ListRecords;

class ListOwnershipTypes extends ListRecords
{
    protected static string $resource = OwnershipTypeResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
