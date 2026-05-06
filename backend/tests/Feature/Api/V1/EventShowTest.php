<?php

use App\Models\Event;
use App\Models\EventCategory;
use App\Models\EventInstance;
use App\Models\Venue;
use Tests\Concerns\RefreshDatabaseWithSchema;

uses(RefreshDatabaseWithSchema::class);

test('returns_200_for_existing_public_event_instance', function () {
    $event = Event::factory()->create([
        'status' => 'approved',
        'attendance_mode' => 'mixed',
        'online_url' => 'https://example.org/stream',
    ]);

    $venue = Venue::factory()->create([
        'address_raw' => 'Москва, ул. Пушкина, д. 1',
    ]);
    $event->venues()->attach($venue->id);

    $eventInstance = EventInstance::factory()->create([
        'event_id' => $event->id,
        'status' => 'scheduled',
    ]);

    $response = $this->getJson("/api/v1/events/{$eventInstance->id}");

    $response->assertOk()
        ->assertJsonPath('data.id', $eventInstance->id)
        ->assertJsonPath('data.event_id', $event->id)
        ->assertJsonPath('data.attendance_mode', 'mixed')
        ->assertJsonPath('data.online_url', 'https://example.org/stream')
        ->assertJsonPath('data.venue.id', $venue->id);
});

test('returns_404_for_unknown_id', function () {
    $response = $this->getJson('/api/v1/events/11111111-1111-1111-1111-111111111111');

    $response->assertNotFound();
});

test('returns_404_for_non_public_event', function () {
    $event = Event::factory()->create([
        'status' => 'draft',
    ]);

    $eventInstance = EventInstance::factory()->create([
        'event_id' => $event->id,
        'status' => 'scheduled',
    ]);

    $response = $this->getJson("/api/v1/events/{$eventInstance->id}");

    $response->assertNotFound();
});

test('response_shape_matches_event_instance_item_contract', function () {
    $eventCategory = EventCategory::factory()->create([
        'name' => 'Лекция',
        'slug' => 'lekciya',
    ]);

    $event = Event::factory()->create([
        'status' => 'approved',
        'attendance_mode' => 'offline',
        'online_url' => null,
    ]);
    $event->categories()->attach($eventCategory->id);

    $venue = Venue::factory()->create();
    $event->venues()->attach($venue->id);

    $eventInstance = EventInstance::factory()->create([
        'event_id' => $event->id,
        'status' => 'scheduled',
    ]);

    $response = $this->getJson("/api/v1/events/{$eventInstance->id}");

    $response->assertOk()
        ->assertJsonStructure([
            'data' => [
                'id',
                'event_id',
                'title',
                'description',
                'attendance_mode',
                'online_url',
                'start_datetime',
                'end_datetime',
                'status',
                'venue' => [
                    'id',
                    'address',
                    'coordinates',
                ],
                'categories' => [
                    '*' => [
                        'id',
                        'name',
                        'slug',
                    ],
                ],
                'organizer' => [
                    'id',
                    'type',
                    'name',
                ],
            ],
        ])
        ->assertJsonPath('data.id', $eventInstance->id)
        ->assertJsonPath('data.event_id', $event->id);
});
