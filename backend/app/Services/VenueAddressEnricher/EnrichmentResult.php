<?php

namespace App\Services\VenueAddressEnricher;

/**
 * DTO for result of a single venue address enrichment (by address or by coordinates).
 */
final class EnrichmentResult
{
    public const STATUS_SUCCESS = 'success';

    public const STATUS_NOT_FOUND = 'not_found';

    public const STATUS_ERROR = 'error';

    public function __construct(
        public readonly string $status,
        public readonly ?string $fiasId = null,
        public readonly ?string $fiasLevel = null,
        public readonly ?string $cityFiasId = null,
        public readonly ?string $kladrId = null,
        public readonly ?string $regionIso = null,
        public readonly ?string $regionCode = null,
        public readonly ?float $lat = null,
        public readonly ?float $lon = null,
        public readonly ?string $errorMessage = null
    ) {}

    public static function success(
        ?string $fiasId = null,
        ?string $fiasLevel = null,
        ?string $cityFiasId = null,
        ?string $kladrId = null,
        ?string $regionIso = null,
        ?string $regionCode = null,
        ?float $lat = null,
        ?float $lon = null
    ): self {
        return new self(
            status: self::STATUS_SUCCESS,
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

    public static function notFound(): self
    {
        return new self(status: self::STATUS_NOT_FOUND);
    }

    public static function error(string $message): self
    {
        return new self(status: self::STATUS_ERROR, errorMessage: $message);
    }

    public function isSuccess(): bool
    {
        return $this->status === self::STATUS_SUCCESS;
    }
}
