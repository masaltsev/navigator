<?php

namespace App\Filament\Resources\VenueResource\Pages;

use App\Filament\Resources\VenueResource;
use Filament\Actions;
use Filament\Resources\Pages\EditRecord;

class EditVenue extends EditRecord
{
    protected static string $resource = VenueResource::class;

    protected ?float $latitudeForCoords = null;

    protected ?float $longitudeForCoords = null;

    /**
     * @param  array<string, mixed>  $data
     * @return array<string, mixed>
     */
    protected function mutateFormDataBeforeFill(array $data): array
    {
        $coords = $this->record->coordinates_array;
        $data['latitude'] = $coords['lat'] ?? null;
        $data['longitude'] = $coords['lng'] ?? null;

        return $data;
    }

    /**
     * @param  array<string, mixed>  $data
     * @return array<string, mixed>
     */
    protected function mutateFormDataBeforeSave(array $data): array
    {
        if (array_key_exists('latitude', $data)) {
            $this->latitudeForCoords = $data['latitude'] !== null && $data['latitude'] !== ''
                ? (float) $data['latitude']
                : null;
            unset($data['latitude']);
        }
        if (array_key_exists('longitude', $data)) {
            $this->longitudeForCoords = $data['longitude'] !== null && $data['longitude'] !== ''
                ? (float) $data['longitude']
                : null;
            unset($data['longitude']);
        }

        return $data;
    }

    protected function afterSave(): void
    {
        if ($this->latitudeForCoords !== null && $this->longitudeForCoords !== null) {
            $this->record->updateCoordinatesFromLatLng($this->latitudeForCoords, $this->longitudeForCoords);
        }
        $this->latitudeForCoords = null;
        $this->longitudeForCoords = null;
    }

    protected function getHeaderActions(): array
    {
        return [
            Actions\DeleteAction::make(),
        ];
    }
}
