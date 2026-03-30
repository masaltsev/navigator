<?php

namespace App\Filament\Resources\ParseProfileResource\Pages;

use App\Filament\Resources\ParseProfileResource;
use Filament\Actions;
use Filament\Resources\Pages\ListRecords;

class ListParseProfiles extends ListRecords
{
    protected static string $resource = ParseProfileResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
