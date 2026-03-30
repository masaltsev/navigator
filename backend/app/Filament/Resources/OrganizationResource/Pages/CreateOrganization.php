<?php

namespace App\Filament\Resources\OrganizationResource\Pages;

use App\Filament\Resources\OrganizationResource;
use Filament\Resources\Pages\CreateRecord;

class CreateOrganization extends CreateRecord
{
    protected static string $resource = OrganizationResource::class;

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
