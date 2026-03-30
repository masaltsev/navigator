<?php

namespace App\Filament\Resources\VenueResource\Pages;

use App\Filament\Resources\VenueResource;
use Filament\Resources\Pages\CreateRecord;

class CreateVenue extends CreateRecord
{
    protected static string $resource = VenueResource::class;

    protected ?float $latitudeForCoords = null;

    protected ?float $longitudeForCoords = null;

    /**
     * @param  array<string, mixed>  $data
     * @return array<string, mixed>
     */
    protected function mutateFormDataBeforeCreate(array $data): array
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

    protected function afterCreate(): void
    {
        if ($this->latitudeForCoords !== null && $this->longitudeForCoords !== null) {
            $this->record->updateCoordinatesFromLatLng($this->latitudeForCoords, $this->longitudeForCoords);
        }
    }
}
