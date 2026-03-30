<?php

namespace App\Filament\Resources\TargetAudienceResource\Pages;

use App\Filament\Resources\TargetAudienceResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditTargetAudience extends EditRecord
{
    protected static string $resource = TargetAudienceResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
