<?php

use App\Models\Organization;
use App\Models\OrganizationType;
use App\Models\Organizer;
use App\Models\OwnershipType;
use App\Models\Source;
use App\Models\ThematicCategory;

beforeEach(function () {
    config(['internal.api_token' => 'test-token']);
});

function sourceTestHeaders(): array
{
    return ['Authorization' => 'Bearer test-token'];
}

function createOrganizationWithOrganizer(): array
{
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();
    if (! $orgType || ! $ownership) {
        return [];
    }

    $data = [
        'source_reference' => 'source_test_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Source Test Org',
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.90,
            'works_with_elderly' => true,
        ],
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
        ],
    ];

    $response = test()->postJson('/api/internal/import/organizer', $data, sourceTestHeaders());
    $response->assertCreated();

    return [
        'organizer_id' => $response->json('organizer_id'),
        'entity_id' => $response->json('entity_id'),
    ];
}

test('GET /api/internal/sources/{id} returns one source', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $source = Source::create([
        'organizer_id' => $ids['organizer_id'],
        'base_url' => 'https://show-test.example.com',
        'kind' => 'org_website',
        'name' => 'Show Test',
        'last_status' => 'pending',
        'is_active' => true,
        'entry_points' => [],
    ]);

    $response = $this->getJson('/api/internal/sources/'.$source->id, sourceTestHeaders());

    $response->assertOk()
        ->assertJsonPath('data.id', $source->id)
        ->assertJsonPath('data.base_url', 'https://show-test.example.com')
        ->assertJsonPath('data.organizer_id', $ids['organizer_id'])
        ->assertJsonPath('data.kind', 'org_website');
});

test('GET /api/internal/sources/{id} returns 404 for unknown id', function () {
    $uuid = '00000000-0000-0000-0000-000000000000';
    $response = $this->getJson('/api/internal/sources/'.$uuid, sourceTestHeaders());
    $response->assertNotFound();
});

test('GET /api/internal/sources/due returns sources due for crawling', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $source = Source::create([
        'organizer_id' => $ids['organizer_id'],
        'base_url' => 'https://due-test-'.uniqid().'.example.com',
        'kind' => 'org_website',
        'name' => 'Due Test',
        'last_status' => 'pending',
        'last_crawled_at' => null,
        'is_active' => true,
        'entry_points' => [],
    ]);

    $response = $this->getJson('/api/internal/sources/due?limit=500', sourceTestHeaders());

    $response->assertOk()
        ->assertJsonStructure(['data' => [['id', 'base_url', 'organizer_id', 'existing_entity_id', 'source_item_id', 'kind']]]);

    $data = $response->json('data');
    $idsReturned = collect($data)->pluck('id')->map(fn ($id) => (string) $id)->all();
    expect($idsReturned)->toContain((string) $source->id);

    $found = collect($data)->firstWhere('id', (string) $source->id);
    expect($found['base_url'])->toBe($source->base_url)
        ->and($found['existing_entity_id'])->toBe($ids['organizer_id']);
});

test('GET /api/internal/sources requires organizer_id', function () {
    $response = $this->getJson('/api/internal/sources', sourceTestHeaders());
    $response->assertUnprocessable()
        ->assertJsonValidationErrors(['organizer_id']);
});

test('GET /api/internal/sources returns list for organizer', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $source = Source::create([
        'organizer_id' => $ids['organizer_id'],
        'base_url' => 'https://example.com/list-test',
        'kind' => 'org_website',
        'name' => 'List Test',
        'last_status' => 'pending',
        'is_active' => true,
        'entry_points' => [],
    ]);

    $response = $this->getJson('/api/internal/sources?organizer_id='.$ids['organizer_id'], sourceTestHeaders());

    $response->assertOk()
        ->assertJsonStructure(['data' => [['id', 'name', 'kind', 'base_url', 'last_status', 'is_active']]]);

    expect($response->json('data'))->toHaveCount(1)
        ->and($response->json('data.0.base_url'))->toBe('https://example.com/list-test');
});

test('GET /api/internal/sources filters by kind', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    Source::create([
        'organizer_id' => $ids['organizer_id'],
        'base_url' => 'https://example.com/org-site',
        'kind' => 'org_website',
        'name' => 'Org',
        'last_status' => 'pending',
        'is_active' => true,
        'entry_points' => [],
    ]);
    Source::create([
        'organizer_id' => $ids['organizer_id'],
        'base_url' => 'https://vk.com/club123',
        'kind' => 'vk_group',
        'name' => 'VK',
        'last_status' => 'pending',
        'is_active' => true,
        'entry_points' => [],
    ]);

    $response = $this->getJson('/api/internal/sources?organizer_id='.$ids['organizer_id'].'&kind=vk_group', sourceTestHeaders());

    $response->assertOk();
    expect($response->json('data'))->toHaveCount(1)
        ->and($response->json('data.0.kind'))->toBe('vk_group');
});

test('POST /api/internal/sources accepts aggregator kind registry_fpg', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $response = $this->postJson('/api/internal/sources', [
        'organizer_id' => $ids['organizer_id'],
        'base_url' => 'https://registry-fpg.example.com/org/123',
        'kind' => 'registry_fpg',
        'name' => 'FPG Registry',
    ], sourceTestHeaders());

    $response->assertCreated()
        ->assertJsonPath('kind', 'registry_fpg')
        ->assertJsonPath('status', 'created');
});

test('POST /api/internal/sources creates source and returns 201', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $response = $this->postJson('/api/internal/sources', [
        'organizer_id' => $ids['organizer_id'],
        'base_url' => 'https://new-source.example.com',
        'kind' => 'org_website',
    ], sourceTestHeaders());

    $response->assertCreated()
        ->assertJson([
            'status' => 'created',
            'organizer_id' => $ids['organizer_id'],
            'base_url' => 'https://new-source.example.com',
            'kind' => 'org_website',
        ])
        ->assertJsonStructure(['source_id']);

    $source = Source::find($response->json('source_id'));
    expect($source)->not->toBeNull()
        ->and($source->base_url)->toBe('https://new-source.example.com')
        ->and($source->kind)->toBe('org_website');
});

test('POST /api/internal/sources syncs site_urls when kind is org_website', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $url = 'https://synced-site.example.com';
    $this->postJson('/api/internal/sources', [
        'organizer_id' => $ids['organizer_id'],
        'base_url' => $url,
        'kind' => 'org_website',
    ], sourceTestHeaders())->assertCreated();

    $org = Organization::find($ids['entity_id']);
    expect($org->site_urls)->toContain($url);
});

test('POST /api/internal/sources returns exists when duplicate organizer_id and base_url', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $url = 'https://dup.example.com';
    $first = $this->postJson('/api/internal/sources', [
        'organizer_id' => $ids['organizer_id'],
        'base_url' => $url,
        'kind' => 'org_website',
    ], sourceTestHeaders());
    $first->assertCreated();

    $second = $this->postJson('/api/internal/sources', [
        'organizer_id' => $ids['organizer_id'],
        'base_url' => $url,
        'kind' => 'org_website',
    ], sourceTestHeaders());

    $second->assertOk()
        ->assertJson(['status' => 'exists', 'source_id' => $first->json('source_id')]);
});

test('PATCH /api/internal/sources/{id} updates source', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $source = Source::create([
        'organizer_id' => $ids['organizer_id'],
        'base_url' => 'https://patch-before.example.com',
        'kind' => 'org_website',
        'name' => 'Before',
        'last_status' => 'pending',
        'is_active' => true,
        'entry_points' => [],
    ]);

    $response = $this->patchJson('/api/internal/sources/'.$source->id, [
        'last_status' => 'success',
        'name' => 'After',
    ], sourceTestHeaders());

    $response->assertOk()
        ->assertJson(['status' => 'updated', 'source_id' => $source->id]);

    $source->refresh();
    expect($source->last_status)->toBe('success')
        ->and($source->name)->toBe('After');
});

test('PATCH /api/internal/sources/{id} syncs site_urls when base_url changes for org_website', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $oldUrl = 'https://old-url.example.com';
    $newUrl = 'https://new-url.example.com';

    $source = Source::create([
        'organizer_id' => $ids['organizer_id'],
        'base_url' => $oldUrl,
        'kind' => 'org_website',
        'name' => 'Org',
        'last_status' => 'pending',
        'is_active' => true,
        'entry_points' => [],
    ]);

    $organizer = Organizer::find($ids['organizer_id']);
    $org = $organizer->organizable;
    $org->update(['site_urls' => [$oldUrl]]);

    $this->patchJson('/api/internal/sources/'.$source->id, [
        'base_url' => $newUrl,
    ], sourceTestHeaders())->assertOk();

    $org->refresh();
    expect($org->site_urls)->not->toContain($oldUrl)
        ->and($org->site_urls)->toContain($newUrl);
});

test('PATCH /api/internal/sources/{id} returns 409 when new base_url conflicts with another source', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $existingUrl = 'https://existing.example.com';
    Source::create([
        'organizer_id' => $ids['organizer_id'],
        'base_url' => $existingUrl,
        'kind' => 'org_website',
        'name' => 'Existing',
        'last_status' => 'pending',
        'is_active' => true,
        'entry_points' => [],
    ]);

    $source2 = Source::create([
        'organizer_id' => $ids['organizer_id'],
        'base_url' => 'https://other.example.com',
        'kind' => 'org_website',
        'name' => 'Other',
        'last_status' => 'pending',
        'is_active' => true,
        'entry_points' => [],
    ]);

    $response = $this->patchJson('/api/internal/sources/'.$source2->id, [
        'base_url' => $existingUrl,
    ], sourceTestHeaders());

    $response->assertStatus(409)
        ->assertJson(['status' => 'conflict']);
});

test('PATCH /api/internal/sources/{id} accepts last_crawled_at', function () {
    $ids = createOrganizationWithOrganizer();
    if (empty($ids)) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $source = Source::create([
        'organizer_id' => $ids['organizer_id'],
        'base_url' => 'https://last-crawled-test.example.com',
        'kind' => 'org_website',
        'name' => 'Test',
        'last_status' => 'pending',
        'is_active' => true,
        'entry_points' => [],
    ]);

    $crawledAt = now()->toIso8601String();
    $response = $this->patchJson('/api/internal/sources/'.$source->id, [
        'last_status' => 'success',
        'last_crawled_at' => $crawledAt,
    ], sourceTestHeaders());

    $response->assertOk();
    $source->refresh();
    expect($source->last_status)->toBe('success')
        ->and($source->last_crawled_at)->not->toBeNull();
});

test('PATCH /api/internal/sources/{id} returns 404 for unknown id', function () {
    $uuid = '00000000-0000-0000-0000-000000000000';
    $response = $this->patchJson('/api/internal/sources/'.$uuid, ['last_status' => 'success'], sourceTestHeaders());
    $response->assertNotFound();
});

test('GET /api/internal/sources returns 401 without token', function () {
    $organizer = Organizer::first();
    if (! $organizer) {
        $this->markTestSkipped('No organizers in database');
    }
    $response = $this->getJson('/api/internal/sources?organizer_id='.$organizer->id);
    $response->assertUnauthorized();
});

test('POST /api/internal/sources validates required fields', function () {
    $response = $this->postJson('/api/internal/sources', [], sourceTestHeaders());
    $response->assertUnprocessable()
        ->assertJsonValidationErrors(['organizer_id', 'base_url', 'kind']);
});
