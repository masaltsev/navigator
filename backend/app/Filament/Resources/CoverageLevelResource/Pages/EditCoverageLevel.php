<?php

namespace App\Filament\Resources\CoverageLevelResource\Pages;

use App\Filament\Resources\CoverageLevelResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditCoverageLevel extends EditRecord
{
    protected static string $resource = CoverageLevelResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
