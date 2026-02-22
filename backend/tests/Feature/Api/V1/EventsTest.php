<?php

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
