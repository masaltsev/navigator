<?php

namespace App\Filament\Resources\InitiativeGroupResource\Pages;

use App\Filament\Resources\InitiativeGroupResource;
use Filament\Resources\Pages\CreateRecord;

class CreateInitiativeGroup extends CreateRecord
{
    protected static string $resource = InitiativeGroupResource::class;

    protected function afterCreate(): void
    {
        if ($this->record->organizer()->exists()) {
            return;
        }

        $this->record->organizer()->create([
            'status' => $this->record->status ?? 'approved',
            'contact_phones' => [],
            'contact_emails' => [],
        ]);
    }
}
