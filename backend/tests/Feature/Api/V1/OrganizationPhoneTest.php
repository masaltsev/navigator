<?php

use App\Models\Organization;
use App\Models\Organizer;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

test('GET /api/v1/organizations includes primary_phone in response', function () {
    // Create organizer with contact phones
    $organizer = Organizer::factory()->withPhones()->create();

    // Create organization and associate it with the organizer
    $organization = Organization::factory()->create([
        'status' => 'approved',
    ]);

    // Update organizer to point to this organization
    $organizer->update([
        'organizable_type' => 'Organization',
        'organizable_id' => $organization->id,
    ]);

    $response = $this->getJson('/api/v1/organizations?per_page=10');

    $response->assertSuccessful();

    $data = $response->json('data');
    expect($data)->toBeArray();

    $organizationData = collect($data)->firstWhere('id', $organization->id);
    expect($organizationData)->not->toBeNull();
    expect($organizationData)->toHaveKey('primary_phone');
    expect($organizationData['primary_phone'])->toBe('+7 (999) 123-45-67');
});

test('GET /api/v1/organizations returns null for primary_phone when no contact phones', function () {
    $organizer = Organizer::factory()->create([
        'contact_phones' => [],
    ]);

    $organization = Organization::factory()->create([
        'status' => 'approved',
    ]);

    // Update organizer to point to this organization
    $organizer->update([
        'organizable_type' => 'Organization',
        'organizable_id' => $organization->id,
    ]);

    $response = $this->getJson('/api/v1/organizations?per_page=10');

    $response->assertSuccessful();

    $data = $response->json('data');
    $organizationData = collect($data)->firstWhere('id', $organization->id);
    expect($organizationData)->not->toBeNull();
    expect($organizationData['primary_phone'])->toBeNull();
});

test('GET /api/v1/organizations does not cause N+1 query problem with organizer loading', function () {
    // Create multiple organizations with organizers
    $organizations = Organization::factory()
        ->count(3)
        ->create(['status' => 'approved']);

    // Create organizers for each organization
    foreach ($organizations as $organization) {
        Organizer::factory()->create([
            'organizable_type' => 'Organization',
            'organizable_id' => $organization->id,
        ]);
    }

    // Enable query log
    \DB::enableQueryLog();

    $response = $this->getJson('/api/v1/organizations?per_page=10');

    $response->assertSuccessful();

    $queries = \DB::getQueryLog();

    // Count queries that fetch organizers
    $organizerQueries = collect($queries)->filter(function ($query) {
        return str_contains($query['query'], 'organizers');
    })->count();

    // Should be 1 query for all organizers (eager loading), not N queries
    expect($organizerQueries)->toBeLessThanOrEqual(1);

    \DB::disableQueryLog();
});
