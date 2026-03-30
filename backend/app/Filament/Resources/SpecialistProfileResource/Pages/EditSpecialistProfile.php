<?php

namespace App\Filament\Resources\SpecialistProfileResource\Pages;

use App\Filament\Resources\SpecialistProfileResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditSpecialistProfile extends EditRecord
{
    protected static string $resource = SpecialistProfileResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
