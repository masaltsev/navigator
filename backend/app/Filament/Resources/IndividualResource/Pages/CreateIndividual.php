<?php

namespace App\Filament\Resources\IndividualResource\Pages;

use App\Filament\Resources\IndividualResource;
use Filament\Resources\Pages\CreateRecord;

class CreateIndividual extends CreateRecord
{
    protected static string $resource = IndividualResource::class;

    protected function afterCreate(): void
    {
        if ($this->record->organizer()->exists()) {
            return;
        }

        $this->record->organizer()->create([
            'status' => 'approved',
            'contact_phones' => [],
            'contact_emails' => [],
        ]);
    }
}
