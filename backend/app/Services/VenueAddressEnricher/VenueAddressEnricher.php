<?php

namespace App\Services\VenueAddressEnricher;

use App\Models\Venue;
use App\Services\Dadata\DadataClient;
use Illuminate\Support\Facades\DB;

/**
 * Enriches venue address data via DaData: fias_id (settlement/city), kladr_id, region_iso, coordinates.
 */
class VenueAddressEnricher
{
    public function __construct(
        protected DadataClient $dadata
    ) {}

    /**
     * Enrich venue using address_raw. Fills fias_id (settlement/city level), optionally kladr_id, region_iso, coordinates.
     */
    public function enrichByAddress(Venue $venue): EnrichmentResult
    {
        $raw = $venue->address_raw ?? '';
        $raw = trim($raw);
        if ($raw === '') {
            return EnrichmentResult::error('address_raw is empty');
        }

        $data = $this->dadata->suggestAddress($raw);
        if ($data === null) {
            $data = $this->dadata->cleanAddress($raw);
        }
        if ($data === null) {
            return EnrichmentResult::notFound();
        }

        return $this->mapDataToResult($data, $raw);
    }

    /**
     * Enrich venue using only Clean API (cleaner.dadata.ru). Use when suggest quota is exhausted.
     * Same result shape as enrichByAddress; requires DADATA_SECRET_KEY.
     */
    public function enrichByAddressCleanOnly(Venue $venue): EnrichmentResult
    {
        $raw = $venue->address_raw ?? '';
        $raw = trim($raw);
        if ($raw === '') {
            return EnrichmentResult::error('address_raw is empty');
        }

        $data = $this->dadata->cleanAddress($raw);
        if ($data === null) {
            return EnrichmentResult::notFound();
        }

        return $this->mapDataToResult($data, $raw);
    }

    /**
     * Enrich venue using coordinates (reverse geocode). Use for venues without address_raw but with coordinates.
     */
    public function enrichByCoordinates(Venue $venue): EnrichmentResult
    {
        $point = $this->getVenueCoordinates($venue);
        if ($point === null) {
            return EnrichmentResult::error('coordinates are empty or invalid');
        }

        $data = $this->dadata->reverseGeocode($point['lat'], $point['lon']);
        if ($data === null) {
            return EnrichmentResult::notFound();
        }

        return $this->mapDataToResult($data);
    }

    /**
     * @return array{lat: float, lon: float}|null
     */
    protected function getVenueCoordinates(Venue $venue): ?array
    {
        $row = DB::selectOne(
            'SELECT ST_Y(coordinates) as lat, ST_X(coordinates) as lon FROM venues WHERE id = ? AND coordinates IS NOT NULL',
            [$venue->id]
        );
        if ($row === null || $row->lat === null || $row->lon === null) {
            return null;
        }

        return [
            'lat' => (float) $row->lat,
            'lon' => (float) $row->lon,
        ];
    }

    /**
     * Map DaData suggestion "data" to EnrichmentResult. FIAS at settlement/city level.
     * city_fias_id: for API filter "by city"; from data or resolved from address when missing.
     * For federal cities (Moscow, Saint Petersburg, Sevastopol) with fias_level=1, city_fias_id = fias_id.
     *
     * @param  array<string, mixed>  $data
     */
    protected function mapDataToResult(array $data, ?string $addressRaw = null): EnrichmentResult
    {
        $fiasId = $this->pickSettlementOrCityFiasId($data);
        $fiasLevel = $this->pickFiasLevelForStoredId($data);
        $cityFiasId = $this->pickCityFiasId($data, $addressRaw);
        $kladrId = $this->pickKladrId($data);
        $regionIso = isset($data['region_iso_code']) && is_string($data['region_iso_code'])
            ? $data['region_iso_code']
            : null;
        $regionCode = $this->pickRegionCode($data);
        $lat = $this->parseCoord($data['geo_lat'] ?? null);
        $lon = $this->parseCoord($data['geo_lon'] ?? null);

        // For federal cities (Moscow, Saint Petersburg, Sevastopol): if fias_level=1, city_fias_id = fias_id
        if ($fiasLevel === '1' && $regionIso !== null && in_array($regionIso, ['RU-MOW', 'RU-SPE', 'RU-SEV'], true)) {
            $cityFiasId = $fiasId;
        }

        // For settlements (level 6): if city_fias_id is still empty, use fias_id as fallback
        // This allows filtering by settlement when city is not available
        if ($cityFiasId === null && $fiasLevel === '6' && $fiasId !== null) {
            $cityFiasId = $fiasId;
        }

        // For regions (level 1) that are not federal cities: if city_fias_id is still empty, use fias_id as fallback
        // This allows filtering by region when city is not available
        if ($cityFiasId === null && $fiasLevel === '1' && $fiasId !== null) {
            $cityFiasId = $fiasId;
        }

        return EnrichmentResult::success(
            fiasId: $fiasId,
            fiasLevel: $fiasLevel,
            cityFiasId: $cityFiasId,
            kladrId: $kladrId,
            regionIso: $regionIso,
            regionCode: $regionCode,
            lat: $lat,
            lon: $lon
        );
    }

    /**
     * City FIAS id for filter: from data.city_fias_id, or resolve from address (e.g. "г Вологда" → suggest "Вологда").
     *
     * @param  array<string, mixed>  $data
     */
    protected function pickCityFiasId(array $data, ?string $addressRaw): ?string
    {
        $city = $data['city_fias_id'] ?? null;
        if (is_string($city) && $city !== '') {
            return $city;
        }
        if ($addressRaw !== null && $addressRaw !== '') {
            return $this->resolveCityFiasIdFromAddress($addressRaw);
        }

        return null;
    }

    /**
     * Extract city name from address (e.g. "г. Вологда, ул X" → "Вологда") and suggest to get city_fias_id.
     */
    protected function resolveCityFiasIdFromAddress(string $address): ?string
    {
        $name = $this->extractCityNameFromAddress($address);
        if ($name === null || $name === '') {
            return null;
        }
        $suggestion = $this->dadata->suggestAddress($name);
        if ($suggestion === null) {
            return null;
        }
        $cityFiasId = $suggestion['city_fias_id'] ?? null;

        return is_string($cityFiasId) && $cityFiasId !== '' ? $cityFiasId : null;
    }

    /**
     * Extract likely city name from address string (г., город, or first significant part).
     */
    protected function extractCityNameFromAddress(string $address): ?string
    {
        $address = trim($address);
        if ($address === '') {
            return null;
        }
        if (preg_match('/\b(?:г\.?|город)\s+([А-Яа-яёЁ\-]+(?:\s+[А-Яа-яёЁ\-]+)?)\s*(?:,|$)/u', $address, $m)) {
            return trim($m[1]);
        }
        if (preg_match('/^([А-Яа-яёЁ\-]+(?:\s+[А-Яа-яёЁ\-]+)?)\s*,/u', $address, $m)) {
            return trim($m[1]);
        }

        return null;
    }

    /**
     * Level of the object we actually store in fias_id (6=settlement, 4=city, 1=region), not the root address level.
     *
     * @param  array<string, mixed>  $data
     */
    protected function pickFiasLevelForStoredId(array $data): ?string
    {
        if (isset($data['settlement_fias_id']) && is_string($data['settlement_fias_id']) && $data['settlement_fias_id'] !== '') {
            return '6';
        }
        if (isset($data['city_fias_id']) && is_string($data['city_fias_id']) && $data['city_fias_id'] !== '') {
            return '4';
        }
        if (isset($data['region_fias_id']) && is_string($data['region_fias_id']) && $data['region_fias_id'] !== '') {
            return '1';
        }

        return null;
    }

    /**
     * Prefer settlement (населённый пункт) FIAS, then city FIAS.
     *
     * @param  array<string, mixed>  $data
     */
    protected function pickSettlementOrCityFiasId(array $data): ?string
    {
        $settlement = $data['settlement_fias_id'] ?? null;
        if (is_string($settlement) && $settlement !== '') {
            return $settlement;
        }
        $city = $data['city_fias_id'] ?? null;
        if (is_string($city) && $city !== '') {
            return $city;
        }
        $region = $data['region_fias_id'] ?? null;
        if (is_string($region) && $region !== '') {
            return $region;
        }

        return null;
    }

    /**
     * @param  array<string, mixed>  $data
     */
    protected function pickKladrId(array $data): ?string
    {
        $ids = ['house_kladr_id', 'street_kladr_id', 'settlement_kladr_id', 'city_kladr_id', 'region_kladr_id'];
        foreach ($ids as $key) {
            $v = $data[$key] ?? null;
            if (is_string($v) && $v !== '') {
                return $v;
            }
        }

        $v = $data['kladr_id'] ?? null;

        return is_string($v) && $v !== '' ? $v : null;
    }

    protected function parseCoord(mixed $value): ?float
    {
        if (is_numeric($value)) {
            return (float) $value;
        }
        if (is_string($value) && $value !== '') {
            return is_numeric($value) ? (float) $value : null;
        }

        return null;
    }

    /**
     * Extract region_code (region_fias_id) from DaData response when region_iso_code is null.
     * Used for filtering new regions (LNR, DNR, Kherson, Zaporozhye) that don't have ISO codes.
     *
     * @param  array<string, mixed>  $data
     */
    protected function pickRegionCode(array $data): ?string
    {
        // Only extract region_code if region_iso_code is null (new regions)
        $regionIso = $data['region_iso_code'] ?? null;
        if ($regionIso !== null && $regionIso !== '') {
            return null;
        }

        // For regions without ISO code, use region_fias_id as region_code
        $regionFiasId = $data['region_fias_id'] ?? null;
        if (is_string($regionFiasId) && $regionFiasId !== '') {
            return $regionFiasId;
        }

        return null;
    }
}
