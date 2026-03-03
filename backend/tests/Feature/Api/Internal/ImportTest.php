<?php

use App\Models\Event;
use App\Models\Organization;
use App\Models\OrganizationType;
use App\Models\Organizer;
use App\Models\OwnershipType;
use App\Models\Source;
use App\Models\ThematicCategory;

beforeEach(function () {
    config(['internal.api_token' => 'test-token']);
});

function internalHeaders(): array
{
    return ['Authorization' => 'Bearer test-token'];
}

test('POST /api/internal/import/organizer creates Organization with full data', function () {
    $category = ThematicCategory::first();
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $category || ! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $data = [
        'source_reference' => 'test_api_org_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Test API Organization',
        'description' => 'Test organization created via API',
        'inn' => '1234567890',
        'ogrn' => '1234567890123',
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.95,
            'works_with_elderly' => true,
        ],
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
            'thematic_category_codes' => [$category->code],
        ],
        'venues' => [
            [
                'address_raw' => 'г. Москва, ул. Тестовая, д. 1',
                'geo_lat' => 55.7558,
                'geo_lon' => 37.6173,
                'is_headquarters' => true,
            ],
        ],
    ];

    $response = $this->postJson('/api/internal/import/organizer', $data, internalHeaders());

    $response->assertCreated()
        ->assertJsonStructure([
            'organizer_id',
            'entity_id',
            'assigned_status',
        ]);

    $org = Organization::find($response->json('entity_id'));
    expect($org)->not->toBeNull()
        ->and($org->title)->toBe($data['title'])
        ->and($org->inn)->toBe($data['inn'])
        ->and($org->source_reference)->toBe($data['source_reference']);

    $organizer = Organizer::find($response->json('organizer_id'));
    expect($organizer)->not->toBeNull()
        ->and($organizer->organizable_type)->toBe('Organization')
        ->and($organizer->organizable_id)->toBe($org->id);
});

test('POST /api/internal/import/organizer assigns approved status for high confidence', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $data = [
        'source_reference' => 'test_smart_publish_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Smart Publish Test Org',
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

    $response = $this->postJson('/api/internal/import/organizer', $data, internalHeaders());

    $response->assertCreated();
    expect($response->json('assigned_status'))->toBe('approved');
});

test('POST /api/internal/import/organizer assigns pending_review for low confidence', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $data = [
        'source_reference' => 'test_pending_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Pending Review Test Org',
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.70,
            'works_with_elderly' => true,
        ],
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
        ],
    ];

    $response = $this->postJson('/api/internal/import/organizer', $data, internalHeaders());

    $response->assertCreated();
    expect($response->json('assigned_status'))->toBe('pending_review');
});

test('POST /api/internal/import/organizer validates required fields', function () {
    $response = $this->postJson('/api/internal/import/organizer', [], internalHeaders());

    $response->assertUnprocessable()
        ->assertJsonValidationErrors(['source_reference', 'entity_type', 'title']);
});

test('deduplication by source_reference updates existing organization', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'dedup_src_'.uniqid();
    $baseData = [
        'source_reference' => $sourceRef,
        'entity_type' => 'Organization',
        'title' => 'Original Title',
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

    $first = $this->postJson('/api/internal/import/organizer', $baseData, internalHeaders());
    $first->assertCreated();
    $entityId = $first->json('entity_id');

    $baseData['title'] = 'Updated Title';
    $second = $this->postJson('/api/internal/import/organizer', $baseData, internalHeaders());
    $second->assertCreated();

    expect($second->json('entity_id'))->toBe($entityId);

    $org = Organization::find($entityId);
    expect($org->title)->toBe('Updated Title');
});

test('deduplication by inn when source_reference differs', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $inn = '9876543210';
    $baseData = fn (string $ref) => [
        'source_reference' => $ref,
        'entity_type' => 'Organization',
        'title' => 'INN Dedup Org',
        'inn' => $inn,
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

    $first = $this->postJson('/api/internal/import/organizer', $baseData('ref_a_'.uniqid()), internalHeaders());
    $first->assertCreated();

    $second = $this->postJson('/api/internal/import/organizer', $baseData('ref_b_'.uniqid()), internalHeaders());
    $second->assertCreated();

    expect($second->json('entity_id'))->toBe($first->json('entity_id'));
});

test('organizations without inn get separate records', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $baseData = fn (string $ref) => [
        'source_reference' => $ref,
        'entity_type' => 'Organization',
        'title' => 'No INN Org',
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

    $first = $this->postJson('/api/internal/import/organizer', $baseData('no_inn_a_'.uniqid()), internalHeaders());
    $second = $this->postJson('/api/internal/import/organizer', $baseData('no_inn_b_'.uniqid()), internalHeaders());

    expect($second->json('entity_id'))->not->toBe($first->json('entity_id'));
});

test('vk_group_url is converted to vk_group_id', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $data = [
        'source_reference' => 'vk_test_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'VK URL Test Org',
        'vk_group_url' => 'https://vk.com/club12345678',
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

    $response = $this->postJson('/api/internal/import/organizer', $data, internalHeaders());
    $response->assertCreated();

    $org = Organization::find($response->json('entity_id'));
    expect($org->vk_group_id)->toBe(12345678);
});

test('short_title is persisted on import', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $data = [
        'source_reference' => 'short_title_test_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Комплексный центр социального обслуживания населения г. Вологды',
        'short_title' => 'КЦСОН Вологда',
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

    $response = $this->postJson('/api/internal/import/organizer', $data, internalHeaders());
    $response->assertCreated();

    $org = Organization::find($response->json('entity_id'));
    expect($org->short_title)->toBe('КЦСОН Вологда');
});

test('venues receive geo fields from Harvester', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $fiasId = 'test-fias-'.uniqid();

    $data = [
        'source_reference' => 'venue_geo_test_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Venue Geo Test Org',
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.90,
            'works_with_elderly' => true,
        ],
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
        ],
        'venues' => [
            [
                'address_raw' => 'г. Вологда, ул. Тестовая, 1',
                'fias_id' => $fiasId,
                'fias_level' => '8',
                'city_fias_id' => '023484a5-f98d-4849-82e1-b7e0444b54ef',
                'region_iso' => 'RU-VLG',
                'region_code' => '35',
                'kladr_id' => '3500000100000',
                'geo_lat' => 59.2181,
                'geo_lon' => 39.8886,
                'is_headquarters' => true,
            ],
        ],
    ];

    $response = $this->postJson('/api/internal/import/organizer', $data, internalHeaders());
    $response->assertCreated();

    $org = Organization::find($response->json('entity_id'));
    $venue = $org->venues->first();
    expect($venue)->not->toBeNull()
        ->and($venue->fias_id)->toBe($fiasId)
        ->and($venue->fias_level)->toBe('8')
        ->and($venue->city_fias_id)->toBe('023484a5-f98d-4849-82e1-b7e0444b54ef')
        ->and($venue->region_iso)->toBe('RU-VLG')
        ->and($venue->region_code)->toBe('35')
        ->and($venue->kladr_id)->toBe('3500000100000');
});

test('POST /api/internal/import/event creates event with deduplication', function () {
    $org = Organization::where('status', 'approved')->first();
    if (! $org) {
        $this->markTestSkipped('No approved organizations found');
    }

    $organizer = $org->organizer;
    if (! $organizer) {
        $this->markTestSkipped('Organization has no organizer');
    }

    $sourceRef = 'event_dedup_'.uniqid();

    $data = [
        'source_reference' => $sourceRef,
        'organizer_id' => $organizer->id,
        'title' => 'Test Event Original',
        'attendance_mode' => 'offline',
        'ai_metadata' => [
            'ai_confidence_score' => 0.90,
        ],
    ];

    $first = $this->postJson('/api/internal/import/event', $data, internalHeaders());
    $first->assertCreated();

    $data['title'] = 'Test Event Updated';
    $second = $this->postJson('/api/internal/import/event', $data, internalHeaders());
    $second->assertCreated();

    expect($second->json('event_id'))->toBe($first->json('event_id'));

    $event = Event::find($first->json('event_id'));
    expect($event->title)->toBe('Test Event Updated');
});

test('POST /api/internal/import/batch accepts batch import', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $data = [
        'items' => [
            [
                'source_reference' => 'batch_001_'.uniqid(),
                'entity_type' => 'Organization',
                'title' => 'Batch Org 1',
                'ai_metadata' => [
                    'decision' => 'accepted',
                    'ai_confidence_score' => 0.90,
                    'works_with_elderly' => true,
                ],
                'classification' => [
                    'organization_type_codes' => [$orgType->code],
                    'ownership_type_code' => $ownership->code,
                ],
            ],
            [
                'source_reference' => 'batch_002_'.uniqid(),
                'entity_type' => 'Organization',
                'title' => 'Batch Org 2',
                'ai_metadata' => [
                    'decision' => 'accepted',
                    'ai_confidence_score' => 0.88,
                    'works_with_elderly' => true,
                ],
                'classification' => [
                    'organization_type_codes' => [$orgType->code],
                    'ownership_type_code' => $ownership->code,
                ],
            ],
        ],
    ];

    $response = $this->postJson('/api/internal/import/batch', $data, internalHeaders());

    $response->assertAccepted()
        ->assertJsonStructure([
            'job_id',
            'items_count',
        ]);

    expect($response->json('items_count'))->toBe(2);
});

test('GET /api/internal/organizers lookup by source_reference', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'lookup_test_'.uniqid();
    $createData = [
        'source_reference' => $sourceRef,
        'entity_type' => 'Organization',
        'title' => 'Lookup Test Org',
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

    $create = $this->postJson('/api/internal/import/organizer', $createData, internalHeaders());
    $create->assertCreated();

    $lookup = $this->getJson("/api/internal/organizers?source_reference={$sourceRef}", internalHeaders());
    $lookup->assertOk()
        ->assertJsonStructure(['data' => ['organizer_id', 'entity_type', 'entity_id', 'status']]);

    expect($lookup->json('data.organizer_id'))->toBe($create->json('organizer_id'));
});

test('GET /api/internal/organizers returns 404 for unknown reference', function () {
    $response = $this->getJson('/api/internal/organizers?source_reference=nonexistent_'.uniqid(), internalHeaders());
    $response->assertNotFound();
});

test('GET /api/internal/organizers lookup by source_id', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $createData = [
        'source_reference' => 'lookup_src_id_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Lookup by Source ID Org',
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

    $create = $this->postJson('/api/internal/import/organizer', $createData, internalHeaders());
    $create->assertCreated();
    $organizerId = $create->json('organizer_id');

    $source = Source::create([
        'organizer_id' => $organizerId,
        'base_url' => 'https://example.com/source-lookup-test',
        'kind' => 'org_website',
        'name' => 'Test Source',
        'last_status' => 'pending',
        'is_active' => true,
        'entry_points' => [],
    ]);

    $lookup = $this->getJson('/api/internal/organizers?source_id='.$source->id, internalHeaders());
    $lookup->assertOk()
        ->assertJsonStructure(['data' => ['organizer_id', 'entity_type', 'entity_id', 'status']]);

    expect($lookup->json('data.organizer_id'))->toBe($organizerId);
});

test('GET /api/internal/organizers lookup by inn', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $inn = '1112223334';
    $createData = [
        'source_reference' => 'lookup_inn_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Lookup by INN Org',
        'inn' => $inn,
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

    $create = $this->postJson('/api/internal/import/organizer', $createData, internalHeaders());
    $create->assertCreated();

    $lookup = $this->getJson("/api/internal/organizers?inn={$inn}", internalHeaders());
    $lookup->assertOk()
        ->assertJsonStructure(['data' => ['organizer_id', 'entity_type', 'entity_id', 'status']]);

    expect($lookup->json('data.organizer_id'))->toBe($create->json('organizer_id'));
});

test('GET /api/internal/organizers returns 401 without token', function () {
    $response = $this->getJson('/api/internal/organizers?source_reference=any');
    $response->assertUnauthorized();
});

test('POST /api/internal/import/organizer assigns rejected status when decision is rejected', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $data = [
        'source_reference' => 'rejected_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Rejected Test Org',
        'ai_metadata' => [
            'decision' => 'rejected',
            'ai_confidence_score' => 0.30,
            'works_with_elderly' => false,
        ],
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
        ],
    ];

    $response = $this->postJson('/api/internal/import/organizer', $data, internalHeaders());

    $response->assertCreated();
    expect($response->json('assigned_status'))->toBe('rejected');
});

test('GET /api/internal/organizations/without-sources returns paginated list', function () {
    $response = $this->getJson('/api/internal/organizations/without-sources?per_page=5', internalHeaders());

    $response->assertOk()
        ->assertJsonStructure([
            'data',
            'meta' => ['total', 'page', 'per_page', 'last_page'],
        ]);

    expect($response->json('meta.per_page'))->toBe(5);
});

test('GET /api/internal/organizations/without-sources caps per_page at 500', function () {
    $response = $this->getJson('/api/internal/organizations/without-sources?per_page=1000', internalHeaders());

    $response->assertOk();
    expect($response->json('meta.per_page'))->toBe(500);
});

test('GET /api/internal/organizations/without-sources items have required fields', function () {
    $response = $this->getJson('/api/internal/organizations/without-sources?per_page=5', internalHeaders());
    $response->assertOk()
        ->assertJsonStructure([
            'data' => [
                '*' => ['org_id', 'organizer_id', 'title', 'inn'],
            ],
            'meta' => ['total', 'page', 'per_page', 'last_page'],
        ]);

    $data = $response->json('data');
    if (count($data) > 0) {
        expect($data[0])->toHaveKeys(['org_id', 'organizer_id', 'title', 'inn']);
    }
});
