<?php

use App\Models\Venue;

test('GET /api/v1/events returns successful response', function () {
    $response = $this->getJson('/api/v1/events');

    $response->assertSuccessful()
        ->assertJsonStructure([
            'data' => [
                '*' => [
                    'id',
                    'title',
                ],
            ],
        ]);
});

test('GET /api/v1/events returns full event structure when data present', function () {
    $response = $this->getJson('/api/v1/events?per_page=1');

    $response->assertSuccessful()
        ->assertJsonStructure([
            'data',
            'meta' => [
                'current_page',
                'per_page',
                'total',
            ],
        ]);
    $data = $response->json('data');
    if (count($data) > 0) {
        $first = $data[0];
        expect($first)->toHaveKeys([
            'id',
            'event_id',
            'title',
            'attendance_mode',
            'start_datetime',
            'end_datetime',
            'status',
        ]);
        if (isset($first['venue'])) {
            expect($first['venue'])->toHaveKeys(['id', 'address']);
        }
        if (isset($first['categories'])) {
            expect($first['categories'])->toBeArray();
        }
        if (isset($first['organizer'])) {
            expect($first['organizer'])->toHaveKeys(['id', 'type', 'name']);
        }
    }
});

test('GET /api/v1/events pagination works', function () {
    $response = $this->getJson('/api/v1/events?per_page=3');

    $response->assertSuccessful()
        ->assertJsonStructure([
            'data',
            'meta' => [
                'current_page',
                'per_page',
                'total',
            ],
        ])
        ->assertJson([
            'meta' => [
                'per_page' => 3,
            ],
        ]);
    expect(count($response->json('data')))->toBeLessThanOrEqual(3);
});

test('GET /api/v1/events filters by time_frame=today', function () {
    $response = $this->getJson('/api/v1/events?time_frame=today');

    $response->assertSuccessful();
});

test('GET /api/v1/events filters by time_frame=tomorrow', function () {
    $response = $this->getJson('/api/v1/events?time_frame=tomorrow');

    $response->assertSuccessful();
});

test('GET /api/v1/events filters by time_frame=this_week', function () {
    $response = $this->getJson('/api/v1/events?time_frame=this_week');

    $response->assertSuccessful();
});

test('GET /api/v1/events filters by time_frame=this_month', function () {
    $response = $this->getJson('/api/v1/events?time_frame=this_month');

    $response->assertSuccessful();
});

test('GET /api/v1/events filters by attendance_mode=offline', function () {
    $response = $this->getJson('/api/v1/events?attendance_mode=offline');

    $response->assertSuccessful();
});

test('GET /api/v1/events filters by attendance_mode=online', function () {
    $response = $this->getJson('/api/v1/events?attendance_mode=online');

    $response->assertSuccessful();
});

test('GET /api/v1/events filters by attendance_mode=mixed', function () {
    $response = $this->getJson('/api/v1/events?attendance_mode=mixed');

    $response->assertSuccessful();
});

test('GET /api/v1/events combines time_frame and attendance_mode filters', function () {
    $response = $this->getJson('/api/v1/events?time_frame=this_week&attendance_mode=offline');

    $response->assertSuccessful();
});

test('GET /api/v1/events filters by geo-radius for offline events', function () {
    $lat = 55.7558;
    $lng = 37.6173;
    $radiusKm = 10;

    $response = $this->getJson("/api/v1/events?lat={$lat}&lng={$lng}&radius_km={$radiusKm}&attendance_mode=offline");

    $response->assertSuccessful();
});

test('GET /api/v1/events filters by city_fias_id', function () {
    $venue = Venue::whereNotNull('fias_id')->where('fias_id', '!=', '')->first();
    if (! $venue) {
        $this->markTestSkipped('No venues with fias_id found');
    }
    $cityFiasId = substr($venue->fias_id, 0, 36);

    $response = $this->getJson('/api/v1/events?city_fias_id='.urlencode($cityFiasId));

    $response->assertSuccessful();
});

test('GET /api/v1/events filters by regioniso', function () {
    $venue = Venue::whereNotNull('region_iso')->where('region_iso', '!=', '')->first();
    if (! $venue) {
        $this->markTestSkipped('No venues with region_iso found');
    }

    $response = $this->getJson('/api/v1/events?regioniso='.urlencode($venue->region_iso));

    $response->assertSuccessful();
});

test('GET /api/v1/events filters by region_code', function () {
    $venue = Venue::whereNotNull('region_code')->where('region_code', '!=', '')->first();
    if (! $venue) {
        $this->markTestSkipped('No venues with region_code found');
    }

    $response = $this->getJson('/api/v1/events?region_code='.urlencode($venue->region_code));

    $response->assertSuccessful();
});
