<?php

namespace App\Filament\Resources\EventInstanceResource\Pages;

use App\Filament\Resources\EventInstanceResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditEventInstance extends EditRecord
{
    protected static string $resource = EventInstanceResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
