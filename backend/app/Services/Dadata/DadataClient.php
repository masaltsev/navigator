<?php

namespace App\Services\Dadata;

use Illuminate\Http\Client\RequestException;
use Illuminate\Support\Facades\Http;

/**
 * HTTP client for DaData Suggest API (address suggestions and geolocate).
 * Uses config from config/services.php (dadata.api_key, dadata.secret_key, dadata.base_url).
 */
class DadataClient
{
    public function __construct(
        protected string $apiKey,
        protected ?string $secretKey,
        protected string $baseUrl,
        protected string $cleanBaseUrl = ''
    ) {}

    public static function fromConfig(): self
    {
        return new self(
            apiKey: (string) config('services.dadata.api_key', ''),
            secretKey: config('services.dadata.secret_key'),
            baseUrl: rtrim((string) config('services.dadata.base_url', 'https://suggestions.dadata.ru/suggestions/api/4_1/rs'), '/'),
            cleanBaseUrl: rtrim((string) config('services.dadata.clean_base_url', 'https://cleaner.dadata.ru/api/v1'), '/')
        );
    }

    /**
     * Suggest address by query string. Returns first suggestion's data or null.
     *
     * @return array<string, mixed>|null Raw "data" object from first suggestion, or null on failure/empty
     */
    public function suggestAddress(string $query): ?array
    {
        if ($query === '') {
            return null;
        }

        try {
            $response = $this->request('POST', '/suggest/address', [
                'query' => $query,
                'count' => 1,
            ]);

            $suggestions = $response['suggestions'] ?? [];
            $first = $suggestions[0] ?? null;

            return isset($first['data']) ? $first['data'] : null;
        } catch (\Throwable) {
            return null;
        }
    }

    /**
     * Clean/standardize a single address (cleaner.dadata.ru). Use as fallback when suggest returns empty.
     * Requires secret_key. Returns same-shaped "data" as suggest, or null.
     *
     * @return array<string, mixed>|null
     */
    public function cleanAddress(string $query): ?array
    {
        if ($query === '' || $this->cleanBaseUrl === '') {
            return null;
        }

        try {
            $response = $this->requestClean('POST', $this->cleanBaseUrl.'/clean/address', [$query]);
            $first = $response[0] ?? null;

            return is_array($first) ? $first : null;
        } catch (\Throwable) {
            return null;
        }
    }

    /**
     * Reverse geocode: get address data by coordinates (Russia only).
     *
     * @return array<string, mixed>|null Raw "data" object from first suggestion, or null on failure/empty
     */
    public function reverseGeocode(float $lat, float $lon): ?array
    {
        try {
            $response = $this->request('POST', '/geolocate/address', [
                'lat' => $lat,
                'lon' => $lon,
                'count' => 1,
            ]);

            $suggestions = $response['suggestions'] ?? [];
            $first = $suggestions[0] ?? null;

            return isset($first['data']) ? $first['data'] : null;
        } catch (\Throwable) {
            return null;
        }
    }

    /**
     * Find party (organization) by INN or OGRN. Returns first suggestion's data or null.
     *
     * @return array<string, mixed>|null Raw "data" object from first suggestion (inn, ogrn, name, address, phones, emails, etc.)
     */
    public function findPartyById(string $innOrOgrn): ?array
    {
        $innOrOgrn = trim($innOrOgrn);
        if ($innOrOgrn === '') {
            return null;
        }

        try {
            $response = $this->request('POST', '/findById/party', [
                'query' => $innOrOgrn,
                'count' => 1,
            ]);

            $suggestions = $response['suggestions'] ?? [];
            $first = $suggestions[0] ?? null;

            return isset($first['data']) ? $first['data'] : null;
        } catch (\Throwable) {
            return null;
        }
    }

    /**
     * @param  array<string, mixed>  $body
     * @return array<string, mixed>
     *
     * @throws RequestException
     */
    protected function request(string $method, string $path, array $body = []): array
    {
        $url = $this->baseUrl.$path;
        $headers = [
            'Content-Type' => 'application/json',
            'Accept' => 'application/json',
            'Authorization' => 'Token '.$this->apiKey,
        ];
        if ($this->secretKey !== null && $this->secretKey !== '') {
            $headers['X-Secret'] = $this->secretKey;
        }

        $response = Http::withHeaders($headers)
            ->timeout(10)
            ->send($method, $url, ['json' => $body]);

        $response->throw();

        $decoded = $response->json();
        if (! is_array($decoded)) {
            return [];
        }

        return $decoded;
    }

    /**
     * Request to Clean API (cleaner.dadata.ru). Body is JSON array, e.g. [ "address string" ].
     *
     * @param  array<int, mixed>  $body
     * @return array<int, mixed>
     *
     * @throws RequestException
     */
    protected function requestClean(string $method, string $url, array $body = []): array
    {
        $headers = [
            'Content-Type' => 'application/json',
            'Accept' => 'application/json',
            'Authorization' => 'Token '.$this->apiKey,
        ];
        if ($this->secretKey !== null && $this->secretKey !== '') {
            $headers['X-Secret'] = $this->secretKey;
        }

        $response = Http::withHeaders($headers)
            ->timeout(10)
            ->send($method, $url, ['json' => $body]);

        $response->throw();

        $decoded = $response->json();
        if (! is_array($decoded)) {
            return [];
        }

        return $decoded;
    }
}
