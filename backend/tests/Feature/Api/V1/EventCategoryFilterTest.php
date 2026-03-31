<?php

use App\Models\Event;
use App\Models\EventCategory;
use App\Models\EventInstance;
use Tests\Concerns\RefreshDatabaseWithSchema;

uses(RefreshDatabaseWithSchema::class);

test('GET /api/v1/events filters by event_category_id', function () {
    $category1 = EventCategory::factory()->create(['slug' => 'lecture-id']);
    $category2 = EventCategory::factory()->create(['slug' => 'workshop-id']);

    $event1 = Event::factory()->create(['status' => 'approved']);
    $event1->categories()->attach($category1->id);

    $event2 = Event::factory()->create(['status' => 'approved']);
    $event2->categories()->attach($category2->id);

    // Create event instances
    EventInstance::factory()->create([
        'event_id' => $event1->id,
        'status' => 'scheduled',
        'start_datetime' => now()->addDay(),
    ]);

    EventInstance::factory()->create([
        'event_id' => $event2->id,
        'status' => 'scheduled',
        'start_datetime' => now()->addDay(),
    ]);

    $response = $this->getJson("/api/v1/events?event_category_id[]={$category1->id}");

    $response->assertSuccessful();

    $data = $response->json('data');
    expect($data)->toBeArray();

    // Should only return events with category1
    $eventIds = collect($data)->pluck('event_id')->toArray();
    expect($eventIds)->toContain($event1->id);
    expect($eventIds)->not->toContain($event2->id);
});

test('GET /api/v1/events filters by event_category_slug', function () {
    $category1 = EventCategory::factory()->create(['slug' => 'lecture-slug']);
    $category2 = EventCategory::factory()->create(['slug' => 'workshop-slug']);

    $event1 = Event::factory()->create(['status' => 'approved']);
    $event1->categories()->attach($category1->id);

    $event2 = Event::factory()->create(['status' => 'approved']);
    $event2->categories()->attach($category2->id);

    // Create event instances
    EventInstance::factory()->create([
        'event_id' => $event1->id,
        'status' => 'scheduled',
        'start_datetime' => now()->addDay(),
    ]);

    EventInstance::factory()->create([
        'event_id' => $event2->id,
        'status' => 'scheduled',
        'start_datetime' => now()->addDay(),
    ]);

    $response = $this->getJson('/api/v1/events?event_category_slug[]=lecture-slug');

    $response->assertSuccessful();

    $data = $response->json('data');
    expect($data)->toBeArray();

    // Should only return events with lecture category
    $eventIds = collect($data)->pluck('event_id')->toArray();
    expect($eventIds)->toContain($event1->id);
    expect($eventIds)->not->toContain($event2->id);
});

test('GET /api/v1/events filters by multiple event_category_id', function () {
    $category1 = EventCategory::factory()->create();
    $category2 = EventCategory::factory()->create();
    $category3 = EventCategory::factory()->create();

    $event1 = Event::factory()->create(['status' => 'approved']);
    $event1->categories()->attach([$category1->id, $category2->id]);

    $event2 = Event::factory()->create(['status' => 'approved']);
    $event2->categories()->attach($category3->id);

    // Create event instances
    EventInstance::factory()->create([
        'event_id' => $event1->id,
        'status' => 'scheduled',
        'start_datetime' => now()->addDay(),
    ]);

    EventInstance::factory()->create([
        'event_id' => $event2->id,
        'status' => 'scheduled',
        'start_datetime' => now()->addDay(),
    ]);

    $response = $this->getJson("/api/v1/events?event_category_id[]={$category1->id}&event_category_id[]={$category2->id}");

    $response->assertSuccessful();

    $data = $response->json('data');

    // Should return event1 (has both categories) but not event2
    $eventIds = collect($data)->pluck('event_id')->toArray();
    expect($eventIds)->toContain($event1->id);
    expect($eventIds)->not->toContain($event2->id);
});

test('GET /api/v1/events returns categories in response', function () {
    $category = EventCategory::factory()->create(['name' => 'Lecture', 'slug' => 'lecture-response']);

    $event = Event::factory()->create(['status' => 'approved']);
    $event->categories()->attach($category->id);

    EventInstance::factory()->create([
        'event_id' => $event->id,
        'status' => 'scheduled',
        'start_datetime' => now()->addDay(),
    ]);

    $response = $this->getJson('/api/v1/events?per_page=1');

    $response->assertSuccessful();

    $data = $response->json('data');
    $eventData = $data[0];

    expect($eventData['categories'])->toBeArray();
    expect($eventData['categories'][0]['name'])->toBe('Lecture');
    expect($eventData['categories'][0]['slug'])->toBe('lecture-response');
});

test('GET /api/v1/events works with combined filters (category + time_frame)', function () {
    $category = EventCategory::factory()->create();

    $event = Event::factory()->create(['status' => 'approved']);
    $event->categories()->attach($category->id);

    EventInstance::factory()->create([
        'event_id' => $event->id,
        'status' => 'scheduled',
        'start_datetime' => now()->addDay(),
    ]);

    $response = $this->getJson("/api/v1/events?event_category_id[]={$category->id}&time_frame=this_week");

    $response->assertSuccessful();

    $data = $response->json('data');
    expect($data)->toBeArray();
});
