<?php

namespace App\Filament\Resources\CoverageLevelResource\Pages;

use App\Filament\Resources\CoverageLevelResource;
use Filament\Actions;
use Filament\Resources\Pages\ListRecords;

class ListCoverageLevels extends ListRecords
{
    protected static string $resource = CoverageLevelResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
