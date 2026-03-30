<?php

namespace App\Filament\Resources\EventInstanceResource\Pages;

use App\Filament\Resources\EventInstanceResource;
use Filament\Actions;
use Filament\Resources\Pages\ListRecords;

class ListEventInstances extends ListRecords
{
    protected static string $resource = EventInstanceResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
