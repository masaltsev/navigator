<?php

use App\Models\Organization;
use App\Models\OrganizationType;
use App\Models\OwnershipType;

beforeEach(function () {
    config(['internal.api_token' => 'test-token']);
});

function protectionHeaders(): array
{
    return ['Authorization' => 'Bearer test-token'];
}

function baseOrgData(string $sourceRef, array $overrides = []): array
{
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    return array_merge([
        'source_reference' => $sourceRef,
        'entity_type' => 'Organization',
        'title' => 'Test Organization',
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.90,
            'works_with_elderly' => true,
        ],
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
        ],
    ], $overrides);
}

test('verified inn is not overwritten by LLM on re-import', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'verified_inn_'.uniqid();
    $dadataInn = '7700000001';

    $first = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'inn' => $dadataInn,
        'verified_fields' => ['inn' => 'dadata', 'ogrn' => 'dadata'],
    ]), protectionHeaders());
    $first->assertCreated();
    $entityId = $first->json('entity_id');

    $org = Organization::find($entityId);
    expect($org->inn)->toBe($dadataInn);
    expect($org->verified_fields)->toHaveKey('inn');

    $second = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'inn' => '9999999999',
        'title' => 'Updated By LLM',
    ]), protectionHeaders());
    $second->assertCreated();
    expect($second->json('entity_id'))->toBe($entityId);

    $org->refresh();
    expect($org->inn)->toBe($dadataInn);
});

test('verified inn CAN be overwritten by dadata-verified import', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'verified_dadata_override_'.uniqid();
    $originalInn = '7700000002';
    $newInn = '7700000003';

    $first = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'inn' => $originalInn,
        'verified_fields' => ['inn' => 'dadata'],
    ]), protectionHeaders());
    $first->assertCreated();
    $entityId = $first->json('entity_id');

    $second = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'inn' => $newInn,
        'verified_fields' => ['inn' => 'dadata'],
    ]), protectionHeaders());
    $second->assertCreated();

    $org = Organization::find($entityId);
    expect($org->inn)->toBe($newInn);
});

test('approved status is not downgraded on re-import with low confidence', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'status_protection_'.uniqid();

    $first = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.95,
            'works_with_elderly' => true,
        ],
    ]), protectionHeaders());
    $first->assertCreated();
    expect($first->json('assigned_status'))->toBe('approved');
    $entityId = $first->json('entity_id');

    $second = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.60,
            'works_with_elderly' => true,
        ],
    ]), protectionHeaders());
    $second->assertCreated();
    expect($second->json('assigned_status'))->toBe('approved');
});

test('approved + rejected re-import goes to pending_review not rejected', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'status_reject_protection_'.uniqid();

    $first = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.95,
            'works_with_elderly' => true,
        ],
    ]), protectionHeaders());
    $first->assertCreated();
    expect($first->json('assigned_status'))->toBe('approved');

    $second = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'ai_metadata' => [
            'decision' => 'rejected',
            'ai_confidence_score' => 0.30,
            'works_with_elderly' => false,
        ],
    ]), protectionHeaders());
    $second->assertCreated();
    expect($second->json('assigned_status'))->toBe('pending_review');
});

test('null inn does not overwrite existing inn', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'null_inn_test_'.uniqid();
    $originalInn = '1234500001';

    $first = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'inn' => $originalInn,
    ]), protectionHeaders());
    $first->assertCreated();
    $entityId = $first->json('entity_id');

    $second = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef), protectionHeaders());
    $second->assertCreated();

    $org = Organization::find($entityId);
    expect($org->inn)->toBe($originalInn);
});

test('existing venues with fias_id are not removed on re-import', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'venue_protection_'.uniqid();
    $fiasId = 'protected-fias-'.uniqid();

    $first = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'venues' => [
            [
                'address_raw' => 'Москва, Тестовая 1',
                'fias_id' => $fiasId,
                'geo_lat' => 55.75,
                'geo_lon' => 37.61,
                'is_headquarters' => true,
            ],
        ],
    ]), protectionHeaders());
    $first->assertCreated();
    $entityId = $first->json('entity_id');

    $org = Organization::find($entityId);
    expect($org->venues)->toHaveCount(1);
    expect($org->venues->first()->fias_id)->toBe($fiasId);

    $second = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'venues' => [
            [
                'address_raw' => 'Другой адрес без fias',
            ],
        ],
    ]), protectionHeaders());
    $second->assertCreated();

    $org->refresh();
    $org->load('venues');
    $fiasVenues = $org->venues->filter(fn ($v) => $v->fias_id === $fiasId);
    expect($fiasVenues)->toHaveCount(1);
});

test('new venue with fias_id is added to existing org on re-import', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'venue_add_'.uniqid();
    $fiasId1 = 'fias-original-'.uniqid();
    $fiasId2 = 'fias-new-'.uniqid();

    $first = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'venues' => [
            [
                'address_raw' => 'Москва, Тестовая 1',
                'fias_id' => $fiasId1,
                'geo_lat' => 55.75,
                'geo_lon' => 37.61,
            ],
        ],
    ]), protectionHeaders());
    $first->assertCreated();
    $entityId = $first->json('entity_id');

    $second = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'venues' => [
            [
                'address_raw' => 'Москва, Новая 2',
                'fias_id' => $fiasId2,
                'geo_lat' => 55.76,
                'geo_lon' => 37.62,
            ],
        ],
    ]), protectionHeaders());
    $second->assertCreated();

    $org = Organization::find($entityId);
    $org->load('venues');
    expect($org->venues)->toHaveCount(2);
});

test('content_hash skips update when unchanged', function () {
    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'hash_skip_'.uniqid();
    $hash = 'abc123def456';

    $data = baseOrgData($sourceRef, [
        'title' => 'Hash Test Org',
        'content_hash' => $hash,
    ]);

    $first = $this->postJson('/api/internal/import/organizer', $data, protectionHeaders());
    $first->assertCreated();
    $entityId = $first->json('entity_id');

    $org = Organization::find($entityId);
    $updatedAt = $org->updated_at;

    sleep(1);

    $second = $this->postJson('/api/internal/import/organizer', $data, protectionHeaders());
    $second->assertCreated();

    $org->refresh();
    expect($org->updated_at->toDateTimeString())->toBe($updatedAt->toDateTimeString());
});

test('classification is additive on update', function () {
    $categories = \App\Models\ThematicCategory::take(2)->get();

    if ($categories->count() < 2) {
        $this->markTestSkipped('Need at least 2 thematic categories');
    }

    $orgType = OrganizationType::first();
    $ownership = OwnershipType::first();

    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $sourceRef = 'classification_merge_'.uniqid();

    $first = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
            'thematic_category_codes' => [$categories[0]->code],
        ],
    ]), protectionHeaders());
    $first->assertCreated();
    $entityId = $first->json('entity_id');

    $second = $this->postJson('/api/internal/import/organizer', baseOrgData($sourceRef, [
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
            'thematic_category_codes' => [$categories[1]->code],
        ],
    ]), protectionHeaders());
    $second->assertCreated();

    $org = Organization::find($entityId);
    $org->load('thematicCategories');
    expect($org->thematicCategories->pluck('code')->toArray())
        ->toContain($categories[0]->code)
        ->toContain($categories[1]->code);
});
