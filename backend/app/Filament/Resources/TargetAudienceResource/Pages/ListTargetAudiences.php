<?php

namespace App\Filament\Resources\TargetAudienceResource\Pages;

use App\Filament\Resources\TargetAudienceResource;
use Filament\Actions;
use Filament\Resources\Pages\ListRecords;

class ListTargetAudiences extends ListRecords
{
    protected static string $resource = TargetAudienceResource::class;

    protected function getHeaderActions(): array
    {
        return [
            Actions\CreateAction::make(),
        ];
    }
}
