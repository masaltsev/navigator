<?php

use App\Models\EventCategory;
use App\Models\OrganizationType;
use App\Models\OwnershipType;
use App\Models\Service;
use App\Models\SpecialistProfile;
use App\Models\ThematicCategory;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;

uses(RefreshDatabase::class);

beforeEach(function () {
    Cache::forget('v1_dictionaries');
});

test('GET /api/v1/dictionaries returns all 6 dictionaries', function () {
    ThematicCategory::factory()->create();
    Service::factory()->create();
    OrganizationType::factory()->create();
    SpecialistProfile::factory()->create();
    OwnershipType::factory()->create();
    EventCategory::factory()->create();

    $response = $this->getJson('/api/v1/dictionaries');

    $response->assertSuccessful();

    $data = $response->json('data');
    expect($data)->toHaveKeys([
        'thematic_categories',
        'services',
        'organization_types',
        'specialist_profiles',
        'ownership_types',
        'event_categories',
    ]);

    foreach ($data as $dictionary) {
        expect($dictionary)->toBeArray();
    }
});

test('GET /api/v1/dictionaries returns all created records', function () {
    ThematicCategory::factory()->create(['name' => 'Category A']);
    ThematicCategory::factory()->create(['name' => 'Category B']);
    Service::factory()->create(['name' => 'Service A']);
    Service::factory()->create(['name' => 'Service B']);

    $response = $this->getJson('/api/v1/dictionaries');

    $response->assertSuccessful();

    $data = $response->json('data');

    $thematicCategories = collect($data['thematic_categories'])->pluck('name')->all();
    expect($thematicCategories)->toContain('Category A', 'Category B');

    $services = collect($data['services'])->pluck('name')->all();
    expect($services)->toContain('Service A', 'Service B');
});

test('GET /api/v1/dictionaries includes required fields for event_categories', function () {
    EventCategory::factory()->create([
        'name' => 'Test Category',
        'slug' => 'test-category',
        'code' => 'test',
        'icon_url' => 'https://example.com/icon.png',
    ]);

    $response = $this->getJson('/api/v1/dictionaries');

    $response->assertSuccessful();

    $data = $response->json('data');
    $eventCategory = collect($data['event_categories'])->firstWhere('slug', 'test-category');

    expect($eventCategory)->not->toBeNull();
    expect($eventCategory)->toHaveKeys(['id', 'name', 'code', 'slug', 'icon_url']);
    expect($eventCategory['slug'])->toBe('test-category');
    expect($eventCategory['icon_url'])->toBe('https://example.com/icon.png');
});

test('GET /api/v1/dictionaries includes parent_id for hierarchical dictionaries', function () {
    $parent = ThematicCategory::factory()->create();
    $child = ThematicCategory::factory()->create([
        'parent_id' => $parent->id,
    ]);

    $response = $this->getJson('/api/v1/dictionaries');

    $response->assertSuccessful();

    $data = $response->json('data');
    $thematicCategories = $data['thematic_categories'];

    // Find child category
    $childCategory = collect($thematicCategories)->firstWhere('id', (string) $child->id);
    expect($childCategory['parent_id'])->toBe($parent->id);
});

test('GET /api/v1/dictionaries is cached', function () {
    // First request
    $response1 = $this->getJson('/api/v1/dictionaries');
    $response1->assertSuccessful();

    // Enable query log
    \DB::enableQueryLog();

    // Second request should come from cache
    $response2 = $this->getJson('/api/v1/dictionaries');
    $response2->assertSuccessful();

    $queries = \DB::getQueryLog();

    // Should have 0 or very few queries (cached)
    expect(count($queries))->toBeLessThan(10);

    \DB::disableQueryLog();
});
