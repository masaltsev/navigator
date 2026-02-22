<?php

use App\Models\Organization;
use App\Models\OrganizationType;
use App\Models\Organizer;
use App\Models\OwnershipType;
use App\Models\ThematicCategory;

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

    $response = $this->postJson('/api/internal/import/organizer', $data);

    $response->assertCreated()
        ->assertJsonStructure([
            'organizer_id',
            'entity_id',
            'assigned_status',
        ]);

    // Verify in DB
    $org = Organization::find($response->json('entity_id'));
    expect($org)->not->toBeNull()
        ->and($org->title)->toBe($data['title'])
        ->and($org->inn)->toBe($data['inn']);

    $organizer = Organizer::find($response->json('organizer_id'));
    expect($organizer)->not->toBeNull()
        ->and($organizer->organizable_type)->toBe(Organization::class)
        ->and($organizer->organizable_id)->toBe($org->id);
});

test('POST /api/internal/import/organizer assigns approved status for high confidence', function () {
    $category = ThematicCategory::first();
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $category || ! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $data = [
        'source_reference' => 'test_smart_publish_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Smart Publish Test Org',
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.90, // >= 0.85
            'works_with_elderly' => true,
        ],
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
        ],
    ];

    $response = $this->postJson('/api/internal/import/organizer', $data);

    $response->assertCreated();
    // Should be approved due to Smart Publish logic
    expect($response->json('assigned_status'))->toBe('approved');
});

test('POST /api/internal/import/organizer assigns pending_review for low confidence', function () {
    $category = ThematicCategory::first();
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $category || ! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $data = [
        'source_reference' => 'test_pending_'.uniqid(),
        'entity_type' => 'Organization',
        'title' => 'Pending Review Test Org',
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.70, // < 0.85
            'works_with_elderly' => true,
        ],
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
        ],
    ];

    $response = $this->postJson('/api/internal/import/organizer', $data);

    $response->assertCreated();
    expect($response->json('assigned_status'))->toBe('pending_review');
});

test('POST /api/internal/import/organizer validates required fields', function () {
    $response = $this->postJson('/api/internal/import/organizer', []);

    $response->assertUnprocessable()
        ->assertJsonValidationErrors(['source_reference', 'entity_type', 'title']);
});

test('POST /api/internal/import/event creates event', function () {
    $org = Organization::where('status', 'approved')->first();
    if (! $org) {
        $this->markTestSkipped('No approved organizations found');
    }

    $organizer = $org->organizer;
    if (! $organizer) {
        $this->markTestSkipped('Organization has no organizer');
    }

    $data = [
        'source_reference' => 'test_event_'.uniqid(),
        'organizer_id' => $organizer->id,
        'title' => 'Test Event',
        'description' => 'Test event description',
        'attendance_mode' => 'offline',
        'ai_metadata' => [
            'ai_confidence_score' => 0.90,
        ],
    ];

    $response = $this->postJson('/api/internal/import/event', $data);

    $response->assertCreated()
        ->assertJsonStructure([
            'event_id',
        ]);
});

test('POST /api/internal/import/batch accepts batch import', function () {
    $category = ThematicCategory::first();
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $category || ! $orgType || ! $ownership) {
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

    $response = $this->postJson('/api/internal/import/batch', $data);

    $response->assertAccepted()
        ->assertJsonStructure([
            'job_id',
            'items_count',
        ]);

    expect($response->json('items_count'))->toBe(2);
});
