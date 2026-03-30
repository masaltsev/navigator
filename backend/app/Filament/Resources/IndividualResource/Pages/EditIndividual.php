<?php

namespace App\Filament\Resources\IndividualResource\Pages;

use App\Filament\Resources\IndividualResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditIndividual extends EditRecord
{
    protected static string $resource = IndividualResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
