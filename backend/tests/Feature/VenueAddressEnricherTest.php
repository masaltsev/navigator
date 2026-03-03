<?php

use App\Models\Venue;
use App\Services\Dadata\DadataClient;
use App\Services\VenueAddressEnricher\EnrichmentResult;
use App\Services\VenueAddressEnricher\VenueAddressEnricher;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

beforeEach(function () {
    config([
        'services.dadata.api_key' => 'test-key',
        'services.dadata.secret_key' => 'test-secret',
        'services.dadata.base_url' => 'https://suggestions.dadata.ru/suggestions/api/4_1/rs',
        'services.dadata.clean_base_url' => 'https://cleaner.dadata.ru/api/v1',
    ]);
});

test('enrichByAddress extracts settlement fias_id from DaData response', function () {
    $dadataResponse = [
        'suggestions' => [
            [
                'value' => 'г Москва, ул Хабаровская',
                'data' => [
                    'city_fias_id' => '0c5b2444-70a0-4932-980c-b4dc0d3f02b5',
                    'settlement_fias_id' => 'a3762098-8b9f-4c83-9b89-f4653b2a0a1b',
                    'region_iso_code' => 'RU-MOW',
                    'region_kladr_id' => '7700000000000',
                    'geo_lat' => '55.821168',
                    'geo_lon' => '37.82608',
                ],
            ],
        ],
    ];

    Http::fake([
        '*.dadata.ru/*' => Http::response($dadataResponse, 200),
    ]);

    $venue = new Venue;
    $venue->id = (string) Str::uuid();
    $venue->address_raw = 'москва хабар';

    $client = DadataClient::fromConfig();
    $enricher = new VenueAddressEnricher($client);
    $result = $enricher->enrichByAddress($venue);

    expect($result)->toBeInstanceOf(EnrichmentResult::class)
        ->and($result->status)->toBe(EnrichmentResult::STATUS_SUCCESS)
        ->and($result->fiasId)->toBe('a3762098-8b9f-4c83-9b89-f4653b2a0a1b')
        ->and($result->regionIso)->toBe('RU-MOW')
        ->and($result->lat)->toBe(55.821168)
        ->and($result->lon)->toBe(37.82608);
});

test('enrichByAddress uses city_fias_id when settlement_fias_id is empty', function () {
    $dadataResponse = [
        'suggestions' => [
            [
                'value' => 'г Москва',
                'data' => [
                    'city_fias_id' => '0c5b2444-70a0-4932-980c-b4dc0d3f02b5',
                    'settlement_fias_id' => null,
                    'region_iso_code' => 'RU-MOW',
                    'geo_lat' => '55.755826',
                    'geo_lon' => '37.617299',
                ],
            ],
        ],
    ];

    Http::fake([
        '*.dadata.ru/*' => Http::response($dadataResponse, 200),
    ]);

    $venue = new Venue;
    $venue->id = (string) Str::uuid();
    $venue->address_raw = 'Москва';

    $enricher = new VenueAddressEnricher(DadataClient::fromConfig());
    $result = $enricher->enrichByAddress($venue);

    expect($result->status)->toBe(EnrichmentResult::STATUS_SUCCESS)
        ->and($result->fiasId)->toBe('0c5b2444-70a0-4932-980c-b4dc0d3f02b5');
});

test('enrichByAddress returns not_found when suggest and clean both return empty', function () {
    Http::fake([
        'suggestions.dadata.ru/*' => Http::response(['suggestions' => []], 200),
        'cleaner.dadata.ru/*' => Http::response([null], 200),
    ]);

    $venue = new Venue;
    $venue->id = (string) Str::uuid();
    $venue->address_raw = 'nonexistent address xyz';

    $enricher = new VenueAddressEnricher(DadataClient::fromConfig());
    $result = $enricher->enrichByAddress($venue);

    expect($result->status)->toBe(EnrichmentResult::STATUS_NOT_FOUND);
});

test('enrichByAddress uses clean API when suggest returns empty', function () {
    Http::fake([
        'suggestions.dadata.ru/*' => Http::response(['suggestions' => []], 200),
        'cleaner.dadata.ru/*' => Http::response([
            [
                'settlement_fias_id' => 'a91f1ef8-fc50-4335-9931-23ee7fcb999a',
                'region_iso_code' => 'RU-KOS',
                'settlement_kladr_id' => '4400800006600',
                'geo_lat' => '57.6420326',
                'geo_lon' => '41.3890186',
            ],
        ], 200),
    ]);

    $venue = new Venue;
    $venue->id = (string) Str::uuid();
    $venue->address_raw = 'Костромская обл, Красносельский р-н, деревня Ивановское, ул Центральная, д 17';

    $enricher = new VenueAddressEnricher(DadataClient::fromConfig());
    $result = $enricher->enrichByAddress($venue);

    expect($result->status)->toBe(EnrichmentResult::STATUS_SUCCESS)
        ->and($result->fiasId)->toBe('a91f1ef8-fc50-4335-9931-23ee7fcb999a')
        ->and($result->regionIso)->toBe('RU-KOS')
        ->and($result->lat)->toBe(57.6420326)
        ->and($result->lon)->toBe(41.3890186);
});

test('enrichByAddress returns error when address_raw is empty', function () {
    $venue = new Venue;
    $venue->id = (string) Str::uuid();
    $venue->address_raw = '';

    $enricher = new VenueAddressEnricher(DadataClient::fromConfig());
    $result = $enricher->enrichByAddress($venue);

    expect($result->status)->toBe(EnrichmentResult::STATUS_ERROR)
        ->and($result->errorMessage)->toContain('empty');
});
