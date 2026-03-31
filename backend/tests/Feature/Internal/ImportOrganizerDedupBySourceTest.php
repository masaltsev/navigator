<?php

use App\Models\Organization;
use App\Models\Organizer;
use App\Models\Source;
use Tests\Concerns\RefreshDatabaseWithSchema;

uses(RefreshDatabaseWithSchema::class);

test('internal import updates existing organization resolved via sources.base_url', function (): void {
    if (config('database.connections.pgsql.database') === 'navigator_core') {
        $this->markTestSkipped('Refusing to write to production database from tests.');
    }

    config()->set('internal.api_token', 'test-token');

    $orgType = \App\Models\OrganizationType::first();
    $ownership = \App\Models\OwnershipType::first();
    if (! $orgType || ! $ownership) {
        $this->markTestSkipped('Required dictionaries not found');
    }

    $existingOrg = Organization::factory()->create([
        'title' => 'ГАУ СО КЦСОН Федоровского района',
        'inn' => fake()->numerify('##########'),
        'ogrn' => fake()->numerify('#############'),
        'description' => null,
        'status' => 'approved',
    ]);

    $organizer = Organizer::query()->create([
        'organizable_type' => 'Organization',
        'organizable_id' => $existingOrg->id,
        'contact_phones' => [],
        'contact_emails' => [],
        'status' => 'approved',
    ]);

    Source::query()->create([
        'name' => 'ok.ru/group/62131670810722',
        'kind' => 'ok_group',
        'base_url' => 'https://ok.ru/group/62131670810722',
        'entry_points' => [],
        'crawl_period_days' => 7,
        'last_status' => 'success',
        'priority' => 50,
        'is_active' => true,
        'organizer_id' => $organizer->id,
    ]);

    $payload = [
        'source_reference' => 'https://ok.ru/group/62131670810722',
        'entity_type' => 'Organization',
        'title' => 'ГАУ СО КЦСОН Федоровского района',
        'description' => str_repeat('описание ', 50),
        'inn' => null,
        'ogrn' => null,
        'vk_group_url' => null,
        'ok_group_url' => 'https://ok.ru/group/62131670810722',
        'telegram_url' => null,
        'ai_metadata' => [
            'decision' => 'accepted',
            'ai_confidence_score' => 0.99,
            'works_with_elderly' => true,
            'ai_explanation' => null,
            'ai_source_trace' => [],
        ],
        'classification' => [
            'organization_type_codes' => [$orgType->code],
            'ownership_type_code' => $ownership->code,
        ],
    ];

    $resp = $this
        ->withHeader('Authorization', 'Bearer test-token')
        ->postJson('/api/internal/import/organizer', $payload);

    $resp->assertCreated();

    expect($resp->json('entity_id'))->toBe($existingOrg->id);

    $existingOrg->refresh();
    expect($existingOrg->description)->not->toBeNull()
        ->and($existingOrg->ok_group_id)->toBe(62131670810722);

    expect(Organization::query()->count())->toBe(1);
});
