<?php

namespace App\Filament\Resources\SourceResource\Pages;

use App\Filament\Resources\SourceResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditSource extends EditRecord
{
    protected static string $resource = SourceResource::class;

    /**
     * @param  array<string, mixed>  $data
     * @return array<string, mixed>
     */
    protected function mutateFormDataBeforeFill(array $data): array
    {
        $data['last_status'] = $this->record->last_status;
        $data['last_crawled_at'] = $this->record->last_crawled_at;

        return $data;
    }

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
