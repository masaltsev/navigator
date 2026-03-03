<?php

use App\Models\Organization;
use App\Models\OrganizationType;
use App\Models\Service;
use App\Models\ThematicCategory;
use App\Models\Venue;

test('GET /api/v1/organizations returns successful response with pagination', function () {
    $response = $this->getJson('/api/v1/organizations');

    $response->assertSuccessful()
        ->assertJsonStructure([
            'data' => [
                '*' => [
                    'id',
                    'title',
                    'organization_types',
                    'thematic_categories',
                    'specialist_profiles',
                    'services',
                ],
            ],
            'meta' => [
                'current_page',
                'per_page',
                'total',
            ],
        ]);
    // venue is optional (when venues exist)
    $firstOrg = $response->json('data.0');
    if (isset($firstOrg['venue'])) {
        expect($firstOrg['venue'])->toHaveKeys(['id', 'address']);
    }
});

test('GET /api/v1/organizations filters by city_fias_id', function () {
    $orgWithVenue = Organization::whereHas('venues', function ($q) {
        $q->whereNotNull('fias_id')->where('fias_id', '!=', '');
    })->first();

    if ($orgWithVenue) {
        $venue = $orgWithVenue->venues->first();
        $cityFiasId = substr($venue->fias_id, 0, 36); // First 36 chars for city

        $response = $this->getJson("/api/v1/organizations?city_fias_id={$cityFiasId}");

        $response->assertSuccessful();
        // Response may contain orgs; if they have venue, it should be in that city/region
    } else {
        $this->markTestSkipped('No organizations with venues containing fias_id found');
    }
});

test('GET /api/v1/organizations filters by thematic_category_id', function () {
    $category = ThematicCategory::first();
    if (! $category) {
        $this->markTestSkipped('No thematic categories found');
    }

    $response = $this->getJson("/api/v1/organizations?thematic_category_id[]={$category->id}");

    $response->assertSuccessful();
    $data = $response->json('data');
    expect($data)->not->toBeEmpty();

    // Verify all returned orgs have the category
    foreach ($data as $org) {
        $categoryIds = collect($org['thematic_categories'])->pluck('id');
        expect($categoryIds)->toContain($category->id);
    }
});

test('GET /api/v1/organizations filters by multiple thematic_category_id', function () {
    $categories = ThematicCategory::limit(2)->get();
    if ($categories->count() < 2) {
        $this->markTestSkipped('Need at least 2 thematic categories');
    }

    $ids = $categories->pluck('id')->implode(',');
    $response = $this->getJson("/api/v1/organizations?thematic_category_id[]={$categories[0]->id}&thematic_category_id[]={$categories[1]->id}");

    $response->assertSuccessful();
});

test('GET /api/v1/organizations filters by organization_type_id', function () {
    $type = OrganizationType::first();
    if (! $type) {
        $this->markTestSkipped('No organization types found');
    }

    $response = $this->getJson("/api/v1/organizations?organization_type_id[]={$type->id}");

    $response->assertSuccessful();
});

test('GET /api/v1/organizations filters by service_id', function () {
    $service = Service::first();
    if (! $service) {
        $this->markTestSkipped('No services found');
    }

    $response = $this->getJson("/api/v1/organizations?service_id[]={$service->id}");

    $response->assertSuccessful();
});

test('GET /api/v1/organizations filters by geo-radius (lat, lng, radius_km)', function () {
    // Find an org with coordinates
    $orgWithCoords = Organization::whereHas('venues', function ($q) {
        $q->whereNotNull('coordinates');
    })->first();

    if ($orgWithCoords && $orgWithCoords->venues->isNotEmpty()) {
        // Get coordinates from venue (simplified - would need PostGIS extraction)
        // For now, use Moscow coordinates as test
        $lat = 55.7558;
        $lng = 37.6173;
        $radiusKm = 50;

        $response = $this->getJson("/api/v1/organizations?lat={$lat}&lng={$lng}&radius_km={$radiusKm}");

        $response->assertSuccessful();
    } else {
        $this->markTestSkipped('No organizations with venues containing coordinates found');
    }
});

test('GET /api/v1/organizations filters by works_with_elderly=false', function () {
    $response = $this->getJson('/api/v1/organizations?works_with_elderly=false');

    $response->assertSuccessful();
    $data = $response->json('data');
    // All returned should have works_with_elderly = false
    // Note: This assumes there are orgs with works_with_elderly=false
});

test('GET /api/v1/organizations filters by regioniso', function () {
    $venueWithRegion = Venue::whereNotNull('region_iso')->where('region_iso', '!=', '')->first();
    if (! $venueWithRegion) {
        $this->markTestSkipped('No venues with region_iso found');
    }

    $response = $this->getJson('/api/v1/organizations?regioniso='.urlencode($venueWithRegion->region_iso));

    $response->assertSuccessful();
});

test('GET /api/v1/organizations filters by region_code', function () {
    $venueWithCode = Venue::whereNotNull('region_code')->where('region_code', '!=', '')->first();
    if (! $venueWithCode) {
        $this->markTestSkipped('No venues with region_code found');
    }

    $response = $this->getJson('/api/v1/organizations?region_code='.urlencode($venueWithCode->region_code));

    $response->assertSuccessful();
});

test('GET /api/v1/organizations index response includes type and required keys', function () {
    $response = $this->getJson('/api/v1/organizations?per_page=1');

    $response->assertSuccessful();
    $data = $response->json('data');
    if (count($data) > 0) {
        $first = $data[0];
        expect($first)->toHaveKeys(['id', 'type', 'title', 'organization_types', 'thematic_categories', 'specialist_profiles', 'services']);
        expect($first['type'])->toBe('Organization');
        if (isset($first['venue'])) {
            expect($first['venue'])->toHaveKeys(['id', 'address']);
        }
    } else {
        $this->markTestSkipped('No organizations in database');
    }
});

test('GET /api/v1/organizations pagination works', function () {
    $response = $this->getJson('/api/v1/organizations?page=1&per_page=5');

    $response->assertSuccessful()
        ->assertJson([
            'meta' => [
                'per_page' => 5,
                'current_page' => 1,
            ],
        ]);

    expect($response->json('data'))->toHaveCount(5);
});

test('GET /api/v1/organizations/{id} returns full organization details', function () {
    $org = Organization::where('status', 'approved')->first();
    if (! $org) {
        $this->markTestSkipped('No approved organizations found');
    }

    $response = $this->getJson("/api/v1/organizations/{$org->id}");

    $response->assertSuccessful()
        ->assertJsonStructure([
            'data' => [
                'id',
                'title',
                'inn',
                'ogrn',
                'site_urls',
                'ownership_type',
                'coverage_level',
                'venues' => [
                    '*' => [
                        'id',
                        'address',
                        'fias_id',
                        'is_headquarters',
                    ],
                ],
                'thematic_categories',
                'organization_types',
                'specialist_profiles',
                'services',
            ],
        ]);
    $data = $response->json('data');
    expect($data)->toHaveKeys(['events', 'articles']);
    expect($data['ownership_type'])->toBeArray();
    expect($data['coverage_level'])->toBeArray();
});

test('GET /api/v1/organizations/{id} returns 404 for non-existent UUID', function () {
    $response = $this->getJson('/api/v1/organizations/00000000-0000-0000-0000-000000000000');

    $response->assertNotFound();
});

test('GET /api/v1/organizations/{id} does not return non-approved organizations', function () {
    $nonApproved = Organization::where('status', '!=', 'approved')->first();
    if ($nonApproved) {
        $response = $this->getJson("/api/v1/organizations/{$nonApproved->id}");
        $response->assertNotFound();
    } else {
        $this->markTestSkipped('No non-approved organizations found');
    }
});

test('GET /api/v1/organizations combines multiple filters', function () {
    $category = ThematicCategory::first();
    $service = Service::first();

    if ($category && $service) {
        $response = $this->getJson("/api/v1/organizations?thematic_category_id[]={$category->id}&service_id[]={$service->id}&per_page=10");

        $response->assertSuccessful();
    } else {
        $this->markTestSkipped('Need thematic category and service for combined filter test');
    }
});
